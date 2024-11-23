import time
import psutil
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import logging
import socket
import requests
from typing import Dict, List, Optional

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações do InfluxDB
INFLUXDB_URL = 'http://localhost:8086'
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")

# Intervalo de coleta em segundos
COLLECTION_INTERVAL = 5

# Configuração dos alvos para monitoramento de latência
LATENCY_TARGETS = [
    {
        'name': 'google_dns',
        'type': 'tcp',
        'host': '8.8.8.8',
        'port': 53
    }
]

def create_influx_client():
    """Cria e retorna um cliente InfluxDB"""
    return InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG
    )
    

def get_latency() -> float:
    """Verifica latência de conexão TCP"""

    target = LATENCY_TARGETS[0]
    host,port = (target['host'],target['port'])
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host,port))
        latency = (time.time() - start_time) * 1000  # Convertendo para millisegundos
        sock.close()
        return latency
    except Exception as e:
        logger.error(f"Erro ao verificar latência TCP para {host}:{port} - {str(e)}")
        return None
    
    return latency

def get_network_stats() -> Dict[str, float]:
    """Coleta estatísticas de rede em tempo real"""
    try:
        # Obtém as estatísticas iniciais
        net_io_counters = psutil.net_io_counters()
        bytes_sent = net_io_counters.bytes_sent
        bytes_recv = net_io_counters.bytes_recv
        
        # Aguarda um segundo para calcular a taxa
        time.sleep(1)
        
        # Obtém as novas estatísticas
        net_io_counters = psutil.net_io_counters()
        new_bytes_sent = net_io_counters.bytes_sent
        new_bytes_recv = net_io_counters.bytes_recv
        
        # Calcula as taxas em Mbps
        upload_speed = (new_bytes_sent - bytes_sent) * 8 / 1_000_000
        download_speed = (new_bytes_recv - bytes_recv) * 8 / 1_000_000
        
        # Coleta informações adicionais
        packets_sent = net_io_counters.packets_sent
        packets_recv = net_io_counters.packets_recv
        errin = net_io_counters.errin
        errout = net_io_counters.errout
        
        logger.info(f"Download: {download_speed:.2f} Mbps, Upload: {upload_speed:.2f} Mbps")
        return {
            "download_speed": download_speed,
            "upload_speed": upload_speed,
            "packets_sent": packets_sent,
            "packets_recv": packets_recv,
            "errors_in": errin,
            "errors_out": errout
        }
    
    except Exception as e:
        logger.error(f"Erro ao coletar estatísticas de rede: {str(e)}")
        return None

def write_to_influxdb(client, stats:Dict[str, float]):
    """Escreve os resultados no InfluxDB"""
    try:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        

        if stats['download_speed'] < 0 or stats['upload_speed'] < 0 or stats['packets_sent'] < 0 or stats['packets_recv'] < 0:
            return 
        point = Point("network_metrics") \
            .field("download_speed", float(stats["download_speed"])) \
            .field("upload_speed", float(stats["upload_speed"])) \
            .field("packets_sent", int(stats["packets_sent"])) \
            .field("packets_recv", int(stats["packets_recv"])) \
            .field("errors_in", int(stats["errors_in"])) \
            .field("errors_out", int(stats["errors_out"])) \
            .field("latency", float(stats["latency"])) \
            .time(datetime.now())
        
        write_api.write(bucket=INFLUXDB_BUCKET, record=point)
        logger.info("Dados salvos no InfluxDB com sucesso")
        
    except Exception as e:
        logger.error(f"Erro ao escrever no InfluxDB: {str(e)}")

def main():
    """Função principal que executa a coleta contínua"""
    logger.info("Iniciando o monitor de rede e latência em tempo real...")
    client = create_influx_client()
    
    try:
        while True:
            # Coleta estatísticas de rede
            network_stats = get_network_stats()
            network_stats['latency'] = get_latency()
            if network_stats:
                write_to_influxdb(client, network_stats)
            time.sleep(COLLECTION_INTERVAL - 1)
            
    except KeyboardInterrupt:
        logger.info("Encerrando o monitor...")
    except Exception as e:
        logger.error(f"Erro no loop principal: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    main()