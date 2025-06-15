import json

TYPEID_PATH = "resources/typeid.json"
BLUEPRINTS_MATERIALS_PATH = "resources/blueprints_materials.json"

def load_type_ids_json(filename):
	with open(filename, encoding='utf-8') as f:
		data = json.load(f)
	type_dict_by_id = {int(k): v for k, v in data.items()}
	type_dict_by_name = {v.lower(): int(k) for k, v in data.items()}
	return type_dict_by_id, type_dict_by_name

def find_type_id_by_name_local(name, filename=TYPEID_PATH):
	_, type_dict_by_name = load_type_ids_json(filename)
	name = name.lower()
	if name in type_dict_by_name:
		return type_dict_by_name[name]
	for type_name, type_id in type_dict_by_name.items():
		if name in type_name:
			return type_id
	return None

def find_type_name_by_id_local(type_id, filename=TYPEID_PATH):
	type_dict_by_id, _ = load_type_ids_json(filename)
	return type_dict_by_id.get(type_id, None)

def load_blueprints_materials(filename):
	with open(filename, encoding='utf-8') as f:
		return json.load(f)

def get_blueprint_materials(type_id, materials_filename=BLUEPRINTS_MATERIALS_PATH, typeid_filename=TYPEID_PATH):
	all_blueprints = load_blueprints_materials(materials_filename)
	if str(type_id) not in all_blueprints:
		return []
	materials = all_blueprints[str(type_id)]
	results = []
	for mat_id, qty in materials:
		mat_name = find_type_name_by_id_local(mat_id, typeid_filename)
		if not mat_name:
			mat_name = f'Unknown({mat_id})'
		results.append((mat_id, mat_name, qty))
	return results

def get_blueprint_materials_by_name(item_name, materials_filename=BLUEPRINTS_MATERIALS_PATH, typeid_filename=TYPEID_PATH):
	type_id = find_type_id_by_name_local(item_name, typeid_filename)
	if type_id is None:
		raise ValueError(f'[!] Не найден typeID для: "{item_name}"')
	return get_blueprint_materials(type_id, materials_filename, typeid_filename)

# Пример использования:
if __name__ == '__main__':
	item_name = 'Combat Scanner Probe I Blueprint'
	try:
		materials = get_blueprint_materials_by_name(item_name, BLUEPRINTS_MATERIALS_PATH, TYPEID_PATH)
		for mat_id, mat_name, qty in materials:
			print(f'{mat_name} ({mat_id}): {qty}')
	except Exception as e:
		print(e)
