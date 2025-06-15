#!/usr/bin/env python3

import argparse
import requests
import json
import time
import os
from rich.text import Text
from rich.console import Console
from rich.table import Table

from blueprint_graber import get_blueprint_materials_by_name, find_type_id_by_name_local


# === Консоль для вывода (можно переопределять в других модулях) ===
console = Console()

# === Загрузка региона из файла ===
def load_regions(filename='resources/regions.json'):
	if not os.path.exists(filename):
		raise FileNotFoundError(f'Файл {filename} с регионами не найден.')
	with open(filename, 'r', encoding='utf-8') as f:
		return json.load(f)

# === Разрешение имени региона в ID ===
def resolve_region_id_by_name(region_name, region_map):
	for rid, name in region_map.items():
		if name.lower() == region_name.lower():
			return int(rid)
	raise ValueError(f'Регион "{region_name}" не найден. Проверь regions.json или имя.')

# === Учет комиссий и эффективности при расчёте цены ===
def calculate_effective_cost(base_price, broker_fee, station_fee, material_efficiency):
	material_modifier = 1 - (material_efficiency / 100)
	price_with_fees = base_price * (1 + broker_fee + station_fee)
	effective_price = price_with_fees * material_modifier
	return effective_price

# === Получение минимальной цены продажи в регионе ===
def get_lowest_sell_price_by_region(type_id, region_id):
	url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/?order_type=sell&type_id={type_id}'
	try:
		resp = requests.get(url, timeout=10)
		resp.raise_for_status()
		data = resp.json()
		if not data:
			return None
		lowest_order = min(data, key=lambda x: x['price'])
		return lowest_order['price']
	except Exception as e:
		print(f'[!] Ошибка получения цены type_id={type_id}: {e}')
		return None

# === Массовое получение цен на материалы ===
def get_material_prices_by_region(type_ids, region_id):
	price_map = {}
	for tid in type_ids:
		price = get_lowest_sell_price_by_region(tid, region_id)
		if price:
			price_map[tid] = price
	return price_map

# === Основной логический блок, возвращает подробную информацию о чертеже ===
def calculate_blueprint_cost(item_name, region_name, broker_fee=0.03, station_fee=0.1, sales_tax=0.005,
                             material_efficiency=0, time_efficiency_percent=0):
	region_map = load_regions()
	region_id = resolve_region_id_by_name(region_name, region_map)
	item_name_full = item_name + " Blueprint"
	item_id = find_type_id_by_name_local(item_name_full)

	materials, output_qty, production_time = get_blueprint_materials_by_name(item_name_full)
	type_ids = [mat_id for mat_id, _, _ in materials]
	prices = get_material_prices_by_region(type_ids, region_id)

	total_material_cost = 0
	formatted_production_time = production_time * (1 - time_efficiency_percent / 100)

	output = {
		"item_name": item_name_full,
		"item_id": item_id,
		"output_qty": output_qty,
		"production_time": formatted_production_time,
		"materials": [],
		"timestamp": time.strftime("%Y-%m-%d/%H:%M:%S", time.localtime())
	}

	for mat_id, mat_name, qty in materials:
		price = prices.get(mat_id)
		effective_price = calculate_effective_cost(price, broker_fee, station_fee, material_efficiency)
		total_cost = effective_price * qty
		total_material_cost += total_cost
		output["materials"].append({
			"id": mat_id,
			"name": mat_name,
			"qty": qty,
			"price_per_unit": effective_price,
			"total_price": total_cost
		})

	base_item_name = item_name.lower().strip()
	product_id = find_type_id_by_name_local(base_item_name)
	buy_price_per_unit = get_lowest_sell_price_by_region(product_id, region_id)
	buy_price_per_unit_net = buy_price_per_unit * (1 - sales_tax)
	buy_price_total = buy_price_per_unit_net * output_qty

	difference = buy_price_total - total_material_cost
	idiot_index = difference / total_material_cost * 100

	output["total_cost"] = total_material_cost
	output["buy_price"] = buy_price_total
	output["idiot_index"] = idiot_index
	output["profit"] = difference
	return output


# === Пример CLI-интерфейса ===
def main():
	parser = argparse.ArgumentParser(description='Расчёт стоимости крафта чертежа в EVE Online по региону')
	parser.add_argument('-b', '--broker', type=float, default=3, help='Комиссия брокера (%%)')
	parser.add_argument('-s', '--station', type=float, default=10, help='Комиссия станции (%%)')
	parser.add_argument('-t', '--tax', type=float, default=0.5, help='Налог на продажу (%%)')
	parser.add_argument('-me', type=int, default=0, help='Эффективность использования времени (TE, %%)')
	parser.add_argument('-te', type=int, default=0, help='Эффективность использования материалов (ME, %%)')
	parser.add_argument('-i', '--item', type=str, required=True, help='Название чертежа (Blueprint)')
	parser.add_argument('-r', '--region', type=str, default="The Forge", help='Название региона')

	args = parser.parse_args()

	result = calculate_blueprint_cost(
		item_name=args.item,
		region_name=args.region,
		broker_fee=args.broker / 100,
		station_fee=args.station / 100,
		sales_tax=args.tax / 100,
		material_efficiency=args.te,
		time_efficiency_percent=args.me
	)

	text = Text()
	text.append(f"Материалы для: {result['item_name']} (ID: {result['item_id']})\n", style="bold")
	text.append("Производится: ", style="bold")
	text.append(f"{result['output_qty']} ", style="bold green")
	text.append("шт за ", style="bold")
	text.append(f"{int(result['production_time'] // 60)} мин {int(result['production_time'] % 60)} сек", style="bold green")
	text.append(" (", style="bold")
	text.append(f"{result['timestamp']}", style="bold cyan")
	text.append(")", style="bold")
	console.print(text)

	table = Table()
	table.add_column("Материал", style="cyan", no_wrap=True)
	table.add_column("ID", justify="right")
	table.add_column("Кол-во", justify="right")
	table.add_column("Цена за ед.", justify="right")
	table.add_column("Итоговая цена", justify="right")

	for m in result['materials']:
		table.add_row(m['name'], str(m['id']), str(m['qty']),
			f"{m['price_per_unit']:,.2f} ISK", f"{m['total_price']:,.2f} ISK")

	console.print(table)

	diff_style = "green" if result['profit'] >= 0 else "red"
	console.print()
	console.print(f"[bold]Цена постройки:[/] {result['total_cost']:,.2f} ISK")
	console.print(f"[bold]Цена покупки:[/] {result['buy_price']:,.2f} ISK")
	console.print(f"[bold {diff_style}]Индекс Гения:[/] {result['idiot_index']:.2f}% ({result['profit']:,.2f} ISK)")
	console.print()


if __name__ == '__main__':
	main()
