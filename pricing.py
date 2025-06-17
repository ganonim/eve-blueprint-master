import time
import requests
import asyncio
import aiohttp

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

async def get_lowest_sell_price_by_region(session, type_id, region_id=None, retries=3):
	if region_id is None:
		url = 'https://esi.evetech.net/latest/markets/prices/'
	else:
		url = f'https://esi.evetech.net/latest/markets/{region_id}/orders/?order_type=sell&type_id={type_id}'
	for attempt in range(retries):
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
		except aiohttp.ClientResponseError as e:
			if 500 <= e.status < 600:
				await asyncio.sleep(1)  # Подождать и попробовать снова
				continue
			else:
				print(f'[!] Ошибка получения цены type_id={type_id}: {e}')
				return None
		except Exception as e:
			print(f'[!] Ошибка получения цены type_id={type_id}: {e}')
			return None
	return None  # После всех попыток


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
	time_efficiency_percent=0,
	get_blueprint_materials_by_name=None,
	find_blueprint_id_by_name=None
):
	from regions import load_regions, resolve_region_id_by_name

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
