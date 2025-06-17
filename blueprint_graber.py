import json
import os

BLUEPRINTS_MATERIALS_PATH = "resources/blueprints_materials.json"

def load_blueprints_materials(filename=BLUEPRINTS_MATERIALS_PATH):
	if not os.path.exists(filename):
		raise FileNotFoundError(f"Файл не найден: {filename}")
	with open(filename, encoding='utf-8') as f:
		return json.load(f)

def find_blueprint_id_by_name(name, data_or_filename=BLUEPRINTS_MATERIALS_PATH):
	if isinstance(data_or_filename, dict):
		data = data_or_filename
	else:
		data = load_blueprints_materials(data_or_filename)

	name = name.lower()
	# Точное совпадение по product_name
	for tid_str, blueprint in data.items():
		if blueprint.get("product_name", "").lower() == name:
			return tid_str
	# Частичное совпадение по product_name
	for tid_str, blueprint in data.items():
		if name in blueprint.get("product_name", "").lower():
			return tid_str
	return None


def find_blueprint_name_by_id(type_id, data_or_filename=BLUEPRINTS_MATERIALS_PATH):
	data = (
		data_or_filename if isinstance(data_or_filename, dict)
		else load_blueprints_materials(data_or_filename)
	)
	entry = data.get(str(type_id))
	if entry:
		return entry.get("name")
	return None

def get_blueprint_materials_by_name(item_name, data_or_filename=BLUEPRINTS_MATERIALS_PATH):
	data = (
		data_or_filename if isinstance(data_or_filename, dict)
		else load_blueprints_materials(data_or_filename)
	)
	tid_str = find_blueprint_id_by_name(item_name, data)
	if tid_str is None:
		raise ValueError(f'[!] Не найден blueprint по имени: "{item_name}"')
	entry = data[tid_str]

	# Преобразуем материалы в список кортежей (id, имя, количество)
	materials = [
		(mat_id, mat_name, qty)
		for mat_id, mat_name, qty in entry.get("materials", [])
	]

	# Возвращаем весь словарь entry вместе с materials и id в удобном формате
	return {
		"blueprint_id": int(tid_str),
		"product_id": entry.get("product_id"),
		"product_name": entry.get("product_name"),
		"materials": materials,
		"output_qty": entry.get("output_qty", 1),
		"production_time": entry.get("production_time", 0),
		"raw_data": entry  # если надо оригинальный словарь целиком
	}


# 🔍 Пример использования
if __name__ == '__main__':
	item_name = 'Combat Scanner Probe I Blueprint'
	try:
		materials, output_qty, prod_time, actual_name, blueprint_id = get_blueprint_materials_by_name(item_name)
		print(f'Blueprint: {actual_name}')
		print(f'ID: {blueprint_id}')
		print(f'Производится: {output_qty} шт. за {prod_time} сек\n')
		for mat_id, mat_name, qty in materials:
			print(f'{mat_name:30} ({mat_id:>6}): {qty}')
	except Exception as e:
		print(e)
