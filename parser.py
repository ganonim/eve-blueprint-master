import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

TYPEID_PATH = "resources/typeid.json"

def load_type_ids(filename):
	with open(filename, encoding='utf-8') as f:
		data = json.load(f)
	# Преобразуем ключи в int, значения — имена
	type_dict = {int(k): v for k, v in data.items()}
	return type_dict

def get_all_blueprint_ids(filename):
	type_dict = load_type_ids(filename)
	return [type_id for type_id, name in type_dict.items() if 'blueprint' in name.lower()]

def get_blueprint_materials(type_id):
	url = f'https://ref-data.everef.net/blueprints/{type_id}'
	resp = requests.get(url)
	print(f'Запрос blueprint {type_id}')
	if resp.status_code != 200:
		raise RuntimeError(f'❌ Ошибка запроса: статус {resp.status_code}')

	data = resp.json()
	activities = data.get('activities', {})
	manufacturing = activities.get('manufacturing', {})
	materials_dict = manufacturing.get('materials', {})
	products_dict = manufacturing.get('products', {})

	if not materials_dict or not products_dict:
		return None  # игнорируем блюпринты без материалов или продукта

	# Получаем первую (основную) продукцию и её количество
	_, product = next(iter(products_dict.items()))
	output_qty = product.get('quantity', 1)

	# Сохраняем материалы
	materials = []
	for mat_id_str, mat_data in materials_dict.items():
		mat_id = int(mat_id_str)
		qty = mat_data['quantity']
		materials.append([mat_id, qty])

	return {
		'materials': materials,
		'output_qty': output_qty
	}


def main():
	blueprint_ids = get_all_blueprint_ids(TYPEID_PATH)
	all_blueprints = {}

	with ThreadPoolExecutor(max_workers=20) as executor:
		futures = {executor.submit(get_blueprint_materials, bp_id): bp_id for bp_id in blueprint_ids}
		for future in as_completed(futures):
			bp_id = futures[future]
			try:
				materials = future.result()
				if materials:
					all_blueprints[bp_id] = materials
			except Exception as e:
				print(f'⚠️ Ошибка при обработке blueprint {bp_id}: {e}')

	with open('blueprints_materials.json', 'w', encoding='utf-8') as f:
		json.dump(all_blueprints, f, indent=2, ensure_ascii=False)

	print(f'✅ Данные сохранены в blueprints_materials.json')

if __name__ == '__main__':
	main()
