import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import time

FILENAME = 'resources/blueprints_materials.json'
IDS_FILENAME = 'resources/blueprints_ids.json'

def get_type_name(type_id):
	url = f'https://ref-data.everef.net/types/{type_id}'
	resp = requests.get(url)
	if resp.status_code != 200:
		return f"Unknown({type_id})"
	data = resp.json()
	return data.get('name', {}).get('en', f"Unknown({type_id})")

def get_blueprint_materials(type_id):
	url = f'https://ref-data.everef.net/blueprints/{type_id}'
	resp = requests.get(url)
	if resp.status_code != 200:
		print(f'⚠️ Не удалось получить blueprint {type_id}, статус {resp.status_code}')
		return None

	data = resp.json()
	activities = data.get('activities', {})
	manufacturing = activities.get('manufacturing', {})
	materials_dict = manufacturing.get('materials', {})
	products_dict = manufacturing.get('products', {})
	production_time = manufacturing.get('time', None)

	if not materials_dict or not products_dict:
		print(f'⚠️ Для blueprint {type_id} отсутствуют материалы или продукты')
		return None

	product_id_str, product = next(iter(products_dict.items()))
	product_id = int(product_id_str)
	output_qty = product.get('quantity', 1)
	product_name = get_type_name(product_id)

	materials = []
	for mat_id_str, mat_data in materials_dict.items():
		mat_id = int(mat_id_str)
		qty = mat_data['quantity']
		name = get_type_name(mat_id)
		materials.append([mat_id, name, qty])

	return {
		# "blueprint_id": type_id,  # ⛔️ больше не нужен
		"product_id": product_id,
		"product_name": product_name,
		"materials": materials,
		"output_qty": output_qty,
		"production_time": production_time
	}


def get_item_name(type_id):
	url = f'https://ref-data.everef.net/types/{type_id}'
	resp = requests.get(url)
	if resp.status_code != 200:
		return None
	data = resp.json()
	return data.get('name', {}).get('en')

def load_json_file(filename):
	if not os.path.exists(filename):
		return {}
	with open(filename, 'r', encoding='utf-8') as f:
		return json.load(f)

def main():
	blueprint_data = load_json_file(FILENAME)
	blueprint_ids = load_json_file(IDS_FILENAME)

	print(f'ℹ️ Всего ID в списке: {len(blueprint_ids)}')
	print(f'ℹ️ Уже есть в файле: {len(blueprint_data)}')

	to_fetch = []
	for tid in blueprint_ids:
		tid_str = str(tid)
		entry = blueprint_data.get(tid_str)
		if not entry or 'materials' not in entry or 'output_qty' not in entry or 'production_time' not in entry:
			to_fetch.append(tid)

	print(f'🛠️ Нужно дозагрузить: {len(to_fetch)} блюпринтов')

	# Загружаем недостающие блюпринты
	with ThreadPoolExecutor(max_workers=20) as executor:
		futures = {
			executor.submit(get_blueprint_materials, tid): tid
			for tid in to_fetch
		}
		for future in as_completed(futures):
			tid = futures[future]
			try:
				result = future.result()
				if result:
					blueprint_data[str(tid)] = result
					print(f'✅ Загружен blueprint {tid}: {result["product_name"]}')
				else:
					print(f'⚠️ Пропущен blueprint {tid}')
			except Exception as e:
				print(f'⚠️ Ошибка в get_blueprint_materials {tid}: {e}')
			time.sleep(0.02)


	with open(FILENAME, 'w', encoding='utf-8') as f:
		json.dump(blueprint_data, f, indent=2, ensure_ascii=False)

	print(f'✅ Сохранено блюпринтов: {len(blueprint_data)} в {FILENAME}')

if __name__ == '__main__':
	main()
