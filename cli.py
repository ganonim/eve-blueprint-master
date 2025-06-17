import argparse
import asyncio
from rich.text import Text
from rich.console import Console
from rich.table import Table

console = Console()

def print_materials_table(materials):
	table = Table()
	table.add_column("Материал", style="cyan", no_wrap=True)
	table.add_column("ID", justify="right")
	table.add_column("Кол-во", justify="right")
	table.add_column("Цена за ед.", justify="right")
	table.add_column("Итоговая цена", justify="right")

	for m in materials:
		style = "yellow" if m['price_per_unit'] == 0 else None
		table.add_row(
			Text(m['name'], style=style),
			Text(str(m['id'])),
			Text(str(m['qty'])),
			Text(f"{m['price_per_unit']:,.2f} ISK"),
			Text(f"{m['total_price']:,.2f} ISK")
		)
	console.print(table)

def print_summary(result):
	diff_style = "green" if result['profit'] >= 0 else "red"
	console.print()
	console.print(f"[bold]Цена постройки:[/] {result['total_cost']:,.2f} ISK")
	console.print(f"[bold]Цена покупки:[/] {result['buy_price']:,.2f} ISK")
	console.print(f"[bold {diff_style}]Индекс Гения:[/] {result['idiot_index']:.2f}% ({result['profit']:,.2f} ISK)")
	console.print()

def print_region_results_table(results, item_name):
	table = Table(title=f"Цены на '{item_name}' по регионам")
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

async def parse_cli_and_run(calculate_blueprint_cost_async, get_blueprint_materials_by_name, find_blueprint_id_by_name):
	import regions

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
			time_efficiency_percent=args.te,
			get_blueprint_materials_by_name=get_blueprint_materials_by_name,
			find_blueprint_id_by_name=find_blueprint_id_by_name
		)

		if result is None:
			console.print(f"[red]Нет данных для '{args.item}' в регионе '{args.region}'[/red]")
			return

		text = Text()
		text.append(f"Материалы для: {result['item_name']} (ID: {result['item_id']})\n", style="bold")
		text.append("Производится: ", style="bold")
		text.append(f"{result['output_qty']} ", style="bold green")
		text.append("шт за ", style="bold")
		text.append(f"{int(result['production_time'] // 60)} мин {int(result['production_time'] % 60)} сек", style="bold green")
		text.append(" (", style="bold")
		text.append(f"{result['timestamp']}", style="bold cyan")
		text.append(")", style="bold")
		console.print(text)

		print_materials_table(result['materials'])
		print_summary(result)

	else:
		region_map = regions.load_regions()
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
						time_efficiency_percent=args.te,
						get_blueprint_materials_by_name=get_blueprint_materials_by_name,
						find_blueprint_id_by_name=find_blueprint_id_by_name
					)
					if result is not None:
						result['region_name'] = region_name
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
		from tqdm.asyncio import tqdm as async_tqdm
		for coro in async_tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Обработка регионов"):
			res = await coro
			if res is not None:
				results.append(res)

		if not results:
			console.print("[red]Нет данных для выбранного предмета в указанных регионах[/red]")
			return

		results.sort(key=lambda x: x["profit"], reverse=True)
		print_region_results_table(results, args.item)
