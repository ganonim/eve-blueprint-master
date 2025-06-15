import argparse
import requests
import json
import os
from blueprint_graber import get_blueprint_materials_by_name, find_type_id_by_name_local

def load_regions(filename='regions.json'):
	if not os.path.exists(filename):
		raise FileNotFoundError(f'Файл {filename} с регионами не найден. Сначала сгенерируй его.')
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
	parser.add_argument('-i', '--item', required=True, help='Название чертежа (Blueprint)')
	parser.add_argument('-r', '--region', required=True, help='Название региона (например, The Forge)')

	args = parser.parse_args()

	item_name = args.item
	broker_fee = args.broker / 100
	station_fee = args.station / 100
	sales_tax = args.tax / 100
	material_efficiency = args.me

	try:
		region_map = load_regions()
		region_id = resolve_region_id_by_name(args.region, region_map)

		materials = get_blueprint_materials_by_name(item_name)
		type_ids = [mat_id for mat_id, _, _ in materials]
		prices = get_material_prices_by_region(type_ids, region_id)

		print(f'📦 Материалы для: {item_name} в регионе {args.region} (ID: {region_id})')
		print(f'{"Материал":25} {"ID":8} {"Кол-во":>6} {"Цена за ед.":>15} {"Итоговая цена":>20}')
		print('-' * 90)

		total_material_cost = 0

		for mat_id, mat_name, qty in materials:
			price = prices.get(mat_id)
			if price is not None:
				effective_price = calculate_effective_cost(price, broker_fee, station_fee, material_efficiency)
				total_cost = effective_price * qty
				total_material_cost += total_cost
				print(f'{mat_name:25} {mat_id:<8} {qty:6} {effective_price:12.2f} ISK {total_cost:18.2f} ISK')
			else:
				print(f'{mat_name:25} {mat_id:<8} {qty:6} {"Цена неизвестна":>15}')

		print('-' * 90)

		item_id = find_type_id_by_name_local(item_name) - 1
		sell_price = get_lowest_sell_price_by_region(item_id, region_id) or 0

		final_sell_price = sell_price * (1 - sales_tax)
		build_price = total_material_cost

		if build_price > 0 and final_sell_price > 0:
			idiot_index = (final_sell_price - build_price) / build_price * 100
			idiot_index_str = f'{idiot_index:.2f}%'
		else:
			idiot_index_str = 'Недоступно'

		print(f'{"Рыночная цена (после налога):":<50} {final_sell_price:18.2f} ISK')
		print(f'{"Цена постройки объекта:":<50} {build_price:18.2f} ISK')
		print(f'{"Индекс идиота:":<60} {idiot_index_str}')

	except Exception as e:
		print(f'[!!] Ошибка выполнения: {e}')

if __name__ == '__main__':
	main()
