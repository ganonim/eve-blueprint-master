#!/usr/bin/env python3

import argparse
import requests
import asyncio
import aiohttp
import json
import time
import os

from tqdm import tqdm

from rich.text import Text
from rich.console import Console
from rich.style import Style
from rich.table import Table

from blueprint_graber import get_blueprint_materials_by_name, find_blueprint_id_by_name

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

def get_average_sell_price_all_regions(type_id):
	url = f'https://esi.evetech.net/latest/markets/prices/'
	try:
		resp = requests.get(url, timeout=10)
		resp.raise_for_status()
		data = resp.json()
		for item in data:
			if item.get("type_id") == type_id:
				return item.get("average_price")
	except Exception as e:
		print(f'[!] Ошибка получения средней цены по рынку для type_id={type_id}: {e}')
		return None


# === Получение минимальной цены продажи в регионе ===
async def get_lowest_sell_price_by_region(session, type_id, region_id=None):
	if region_id is None:
		url = 'https://esi.evetech.net/latest/markets/prices/'
	else:
		url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/?order_type=sell&type_id={type_id}'
	try:
		async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
			resp.raise_for_status()
			data = await resp.json()
			if region_id is None:
				for item in data:
					if item.get("type_id") == type_id:
						return item.get("average_price")
				return None
			else:
				if not data:
					return None
				lowest_order = min(data, key=lambda x: x['price'])
				return lowest_order['price']
	except Exception as e:
		print(f'[!] Ошибка получения цены type_id={type_id}: {e}')
		return None


# === Массовое получение цен на материалы ===
async def get_material_prices_by_region(type_ids, region_id, session, concurrency=10):
    price_map = {}
    semaphore = asyncio.Semaphore(concurrency)

    async def get_price(tid):
        async with semaphore:
            return tid, await get_lowest_sell_price_by_region(session, tid, region_id)

    tasks = [asyncio.create_task(get_price(tid)) for tid in type_ids]
    for task in asyncio.as_completed(tasks):
        tid, price = await task
        if price:
            price_map[tid] = price
    return price_map

async def calculate_blueprint_cost_async(
	item_name,
	region_name=None,
	broker_fee=0.03,
	station_fee=0.1,
	sales_tax=0.005,
	material_efficiency=0,
	time_efficiency_percent=0
):
	region_id = None
	if region_name:
		region_map = load_regions()
		region_id = resolve_region_id_by_name(region_name, region_map)

	bp_data = get_blueprint_materials_by_name(item_name)

	materials = bp_data["materials"]
	output_qty = bp_data["output_qty"]
	production_time = bp_data["production_time"]
	item_name_right = bp_data["product_name"]
	item_id = bp_data["blueprint_id"]
	product_id = bp_data.get("product_id") or find_blueprint_id_by_name(item_name.lower().strip())

	async with aiohttp.ClientSession() as session:
		buy_price_per_unit = await get_lowest_sell_price_by_region(session, product_id, region_id)
		if not buy_price_per_unit:
			return None
		buy_price_total = buy_price_per_unit * (1 - sales_tax) * output_qty

		type_ids = [mat_id for mat_id, _, _ in materials]
		prices = await get_material_prices_by_region(type_ids, region_id, session)

		if any(price is None or price == 0 for price in prices.values()):
			return None

		total_material_cost = 0
		formatted_production_time = production_time * (1 - time_efficiency_percent / 100)

		output = {
			"item_name": item_name_right,
			"item_id": item_id,
			"output_qty": output_qty,
			"production_time": formatted_production_time,
			"materials": [],
			"timestamp": time.strftime("%Y-%m-%d/%H:%M:%S", time.localtime())
		}

		for mat_id, mat_name, qty in materials:
			price = prices.get(mat_id)
			effective_price = calculate_effective_cost(price or 0, broker_fee, station_fee, material_efficiency)
			total_cost = effective_price * qty
			total_material_cost += total_cost
			output["materials"].append({
				"id": mat_id,
				"name": mat_name,
				"qty": qty,
				"price_per_unit": effective_price,
				"total_price": total_cost
			})

		diff = buy_price_total - total_material_cost
		output["total_cost"] = total_material_cost
		output["buy_price"] = buy_price_total
		output["profit"] = diff
		output["idiot_index"] = (diff / total_material_cost * 100) if total_material_cost > 0 else 0
		return output


# === Пример CLI-интерфейса ===
async def main():
	parser = argparse.ArgumentParser(description='Расчёт стоимости крафта чертежа в EVE Online по региону')
	parser.add_argument('-b', '--broker', type=float, default=3, help='Комиссия брокера (%%)')
	parser.add_argument('-s', '--station', type=float, default=10, help='Комиссия станции (%%)')
	parser.add_argument('-t', '--tax', type=float, default=0.5, help='Налог на продажу (%%)')
	parser.add_argument('-me', type=int, default=0, help='Эффективность использования времени (TE, %%)')
	parser.add_argument('-te', type=int, default=0, help='Эффективность использования материалов (ME, %%)')
	parser.add_argument('-i', '--item', type=str, required=True, help='Название чертежа (Blueprint)')
	parser.add_argument('-r', '--region', type=str, default=None, help='Название региона (если не указан — сравним все)')

	args = parser.parse_args()
 
	if args.region:
		result = await calculate_blueprint_cost_async(
			item_name=args.item,
			region_name=args.region,
			broker_fee=args.broker / 100,
			station_fee=args.station / 100,
			sales_tax=args.tax / 100,
			material_efficiency=args.me,
			time_efficiency_percent=args.te
		)

		text = Text()
		text.append(f"Материалы для: {result["item_name"]} (ID: {result['item_id']})\n", style="bold")
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
			style = None
			if m['price_per_unit'] == 0:
				style = "yellow"
			table.add_row(
				Text(m['name'], style=style),
				Text(str(m['id'])),
				Text(str(m['qty'])),
				Text(f"{m['price_per_unit']:,.2f} ISK"),
				Text(f"{m['total_price']:,.2f} ISK")
    	)

		console.print(table)

		diff_style = "green" if result['profit'] >= 0 else "red"
		console.print()
		console.print(f"[bold]Цена постройки:[/] {result['total_cost']:,.2f} ISK")
		console.print(f"[bold]Цена покупки:[/] {result['buy_price']:,.2f} ISK")
		console.print(f"[bold {diff_style}]Индекс Гения:[/] {result['idiot_index']:.2f}% ({result['profit']:,.2f} ISK)")
		console.print()

	else:
		region_map = load_regions()
		region_ids = range(10000001, 10000071)
		semaphore = asyncio.Semaphore(10)  # ограничение параллелизма

		async def limited_calculate(region_name):
			async with semaphore:
				try:
					result = await calculate_blueprint_cost_async(
						item_name=args.item,
						region_name=region_name,
						broker_fee=args.broker / 100,
						station_fee=args.station / 100,
						sales_tax=args.tax / 100,
						material_efficiency=args.me,
						time_efficiency_percent=args.te
					)
					if result is not None:
						result['region_name'] = region_name  # добавляем имя региона сюда
					return result
				except Exception as e:
					console.print(f"[red][!] Ошибка в регионе '{region_name}': {e}[/red]")
					return None


		tasks = []
		for rid_int in region_ids:
			rid_str = str(rid_int)
			region_name = region_map.get(rid_str)
			if region_name is None:
				continue
			tasks.append(asyncio.create_task(limited_calculate(region_name)))

		results = []
		for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Обработка регионов"):
			res = await coro
			if res is not None:
				results.append(res)

		if not results:
			console.print("[red]Нет данных для выбранного предмета в указанных регионах[/red]")
			return

		results.sort(key=lambda x: x["profit"], reverse=True)

		table = Table(title=f"Цены на '{args.item}' по регионам")
		table.add_column("Регион", style="cyan")
		table.add_column("Себестоимость", justify="right")
		table.add_column("Продажа", justify="right")
		table.add_column("Прибыль", justify="right")
		table.add_column("Индекс", justify="right")

		for res in results:
			missing_resource = any(m['price_per_unit'] == 0 for m in res['materials'])
			row_style = "yellow" if missing_resource else None
			diff_style = "green" if res['profit'] >= 0 else "red"

			if row_style:
				cost_str = "-"
				profit_str = "-"
				index_str = "-"
				profit_style = None
			else:
				cost_str = f"{res['total_cost']:,.2f}"
				profit_str = f"{res['profit']:,.2f}"
				index_str = f"{res['idiot_index']:.2f}%"
				profit_style = diff_style

			table.add_row(
				Text(res["region_name"], style=row_style),
				Text(cost_str),
				Text(f"{res['buy_price']:,.2f}"),
				Text(profit_str, style=profit_style),
				Text(index_str, style=profit_style)
			)



		console.print()
		console.print(table)


if __name__ == '__main__':
	asyncio.run(main())
