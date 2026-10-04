from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook

from lyon_etl import (
    calculate_routes,
    extract_datatourisme,
    extract_osm,
    extract_sirene,
    load_records,
    normalise_datatourisme,
    normalise_osm,
    transform_core,
)


def warehouse_uri() -> str:
    return BaseHook.get_connection("lyon_warehouse").get_uri()


def load_all(**context) -> int:
    records = normalise_osm(context["ti"].xcom_pull(task_ids="extract_osm"))
    datatourisme_path = context["ti"].xcom_pull(task_ids="extract_datatourisme")
    if datatourisme_path:
        records.extend(normalise_datatourisme(datatourisme_path))
    return load_records(records, warehouse_uri())


with DAG(
    dag_id="lyon_nightlife_etl",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={"owner": "data-engineering", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["lyon", "nightlife", "postgis"],
) as dag:
    osm = PythonOperator(task_id="extract_osm", python_callable=extract_osm)
    datatourisme = PythonOperator(task_id="extract_datatourisme", python_callable=extract_datatourisme)
    sirene = PythonOperator(task_id="extract_sirene", python_callable=extract_sirene)
    load = PythonOperator(task_id="load_raw_and_normalize", python_callable=load_all)
    transform = PythonOperator(task_id="transform_core_places", python_callable=lambda: transform_core(warehouse_uri()))
    routes = PythonOperator(task_id="calculate_walking_candidates", python_callable=lambda: calculate_routes(warehouse_uri()))

    [osm, datatourisme, sirene] >> load >> transform >> routes
