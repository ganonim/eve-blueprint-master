import requests
import json

def get_all_region_ids():
	url = 'https://esi.evetech.net/latest/universe/regions/'
	resp = requests.get(url, timeout=10)
	resp.raise_for_status()
	return resp.json()

def get_names_for_ids(ids):
	url = 'https://esi.evetech.net/latest/universe/names/'
	resp = requests.post(url, json=ids, timeout=10)
	resp.raise_for_status()
	return resp.json()

def list_regions_json(filename='regions.json'):
	ids = get_all_region_ids()
	names = get_names_for_ids(ids)
	regions = [item for item in names if item.get('category') == 'region']
	result = {item['id']: item['name'] for item in regions}

	with open(filename, 'w', encoding='utf-8') as f:
		json.dump(result, f, ensure_ascii=False, indent=2)

	print(f'✅ Список регионов сохранён в {filename}')

if __name__ == '__main__':
	list_regions_json()
