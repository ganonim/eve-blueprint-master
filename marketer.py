#!/usr/bin/env python3

import argparse
import requests
import json
import time
import os
from rich.console import Console
from rich.table import Table
from rich import box
from blueprint_graber import get_blueprint_materials_by_name, find_type_id_by_name_local

def load_regions(filename='resources/regions.json'):
	if not os.path.exists(filename):
		raise FileNotFoundError(f'Файл {filename} с регионами не найден.')
	with open(filename, 'r', encoding='utf-8') as f:
		return json.load(f)

def resolve_region_id_by_name(region_name, region_map):
	for rid, name in region_map.items():
		if name.lower() == region_name.lower():
			return int(rid)
	raise ValueError(f'Регион "{region_name}" не найден. Проверь regions.json или имя.')

def calculate_effective_cost(base_price, broker_fee, station_fee, material_efficiency):
	material_modifier = 1 - (material_efficiency / 100)
	price_with_fees = base_price * (1 + broker_fee + station_fee)
	effective_price = price_with_fees * material_modifier
	return effective_price

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

def get_material_prices_by_region(type_ids, region_id):
	price_map = {}
	for tid in type_ids:
		price = get_lowest_sell_price_by_region(tid, region_id)
		if price:
			price_map[tid] = price
	return price_map

def main():
	parser = argparse.ArgumentParser(description='Расчёт стоимости крафта чертежа в EVE Online по региону')
	parser.add_argument('-b', '--broker', type=float, default=3, help='Комиссия брокера (%%)')
	parser.add_argument('-s', '--station', type=float, default=10, help='Комиссия станции (%%)')
	parser.add_argument('-t', '--tax', type=float, default=0.5, help='Налог на продажу (%%)')
	parser.add_argument('-m', '--me', type=int, default=0, help='Эффективность использования материалов (ME, %%)')
	parser.add_argument('-i', '--item', type=str, required=True, help='Название чертежа (Blueprint)')
	parser.add_argument('-r', '--region', type=str, default="The Forge", help='Название региона (например, The Forge)')

	args = parser.parse_args()

	item_name = args.item
	item_id = find_type_id_by_name_local(item_name)
	broker_fee = args.broker / 100
	station_fee = args.station / 100
	sales_tax = args.tax / 100
	material_efficiency = args.me

	local_time = time.localtime()
	formated_time = time.strftime("%Y-%m-%d/%H:%M:%S", local_time)

	try:
		region_map = load_regions()
		region_id = resolve_region_id_by_name(args.region, region_map)

		# 🔧 Тут: получаем материалы и output_qty
		materials, output_qty = get_blueprint_materials_by_name(item_name)
		type_ids = [mat_id for mat_id, _, _ in materials]
		prices = get_material_prices_by_region(type_ids, region_id)

		total_material_cost = 0
		console = Console()
		console.print("")
		console.print(f'[bold]Материалы для: {item_name} (ID: {item_id})\nПроизводится: {output_qty} шт за цикл ({formated_time})')
		console.print("")
		table = Table()
		table.add_column("Материал", style="cyan", no_wrap=True)
		table.add_column("ID", justify="right")
		table.add_column("Кол-во", justify="right")
		table.add_column("Цена за ед.", justify="right")
		table.add_column("Итоговая цена", justify="right")

		for mat_id, mat_name, qty in materials:
			price = prices.get(mat_id)
			if price is not None:
				effective_price = calculate_effective_cost(price, broker_fee, station_fee, material_efficiency)
				total_cost = effective_price * qty
				total_material_cost += total_cost
				table.add_row(mat_name, str(mat_id), str(qty), f"{effective_price:,.2f} ISK", f"{total_cost:,.2f} ISK")
			else:
				table.add_row(mat_name, str(mat_id), str(qty), "[red]Н/Д[/]", "[red]Н/Д[/]")

		console.print(table)

		# Получение ID и рыночной цены производимого предмета
		if item_name.lower().endswith(" blueprint"):
			base_item_name = item_name.lower().replace(" blueprint", "").strip()
		else:
			base_item_name = item_name.lower()

		product_id = find_type_id_by_name_local(base_item_name)
		buy_price_per_unit = get_lowest_sell_price_by_region(product_id, region_id) or 0
		buy_price_per_unit_net = buy_price_per_unit * (1 - sales_tax)

		buy_price_per_units = buy_price_per_unit_net * output_qty 

		console.print()
		console.print(f"[bold]Цена постройки:[/] {total_material_cost:,.2f} ISK")
		console.print(f"[bold]Цена покупки:[/] {buy_price_per_units:,.2f} ISK")

		idiot_index = (buy_price_per_units - total_material_cost) / total_material_cost * 100
		console.print(f"[bold green]Индекс Гения:[/] {idiot_index:.2f}%")
		console.print()

	except Exception as e:
		console.print(f"[bold red][!!] Ошибка выполнения: {e}[/]")


if __name__ == '__main__':
	main()
