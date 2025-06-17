import asyncio
from cli import parse_cli_and_run
from pricing import calculate_blueprint_cost_async
from blueprint_graber import get_blueprint_materials_by_name, find_blueprint_id_by_name

if __name__ == '__main__':
	asyncio.run(parse_cli_and_run(
		calculate_blueprint_cost_async,
		get_blueprint_materials_by_name,
		find_blueprint_id_by_name
	))
