import argparse
import requests
from blueprint_graber import get_blueprint_materials_by_name, find_type_id_by_name_local

def calculate_effective_cost(base_price, broker_fee, station_fee, material_efficiency):
	material_modifier = 1 - (material_efficiency / 100)
	price_with_fees = base_price * (1 + broker_fee + station_fee)
	effective_price = price_with_fees * material_modifier
	return effective_price

def get_prices_esi(type_ids):
	url = 'https://esi.evetech.net/latest/markets/prices/'
	try:
		resp = requests.get(url, timeout=10)
		resp.raise_for_status()
		data = resp.json()
		price_map = {}
		for item in data:
			tid = item['type_id']
			if tid in type_ids:
				price = item.get('average_price') or item.get('adjusted_price')
				price_map[tid] = price
		return price_map
	except Exception as e:
		print(f'Ошибка получения цен из ESI: {e}')
		return {}

def main():
	parser = argparse.ArgumentParser(description='Расчёт стоимости крафта чертежа в EVE Online')
	parser.add_argument('-b', '--broker', type=float, default=3, help='Комиссия брокера (%%)')
	parser.add_argument('-s', '--station', type=float, default=10, help='Комиссия станции (%%)')
	parser.add_argument('-t', '--tax', type=float, default=0.5, help='Налог на продажу (%%)')
	parser.add_argument('-m', '--me', type=int, default=0, help='Эффективность использования материалов (ME, %%)')
	parser.add_argument('-i', '--item', required=True, help='Название чертежа (Blueprint)')



	args = parser.parse_args()

	item_name = args.item
	broker_fee = args.broker / 100
	station_fee = args.station / 100
	sales_tax = args.tax / 100
	material_efficiency = args.me

	try:
		materials = get_blueprint_materials_by_name(item_name)
		type_ids = [mat_id for mat_id, _, _ in materials]
		prices = get_prices_esi(type_ids)

		print(f'📦 Материалы для: {item_name}')
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

		item_id = [find_type_id_by_name_local(item_name) - 1]
		market_price_data = get_prices_esi(item_id)
		sell_price = market_price_data.get(item_id[0], 0)

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
		print(str(e))


if __name__ == '__main__':
	main()
