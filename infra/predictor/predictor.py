import pandas as pd
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import logging
from datetime import datetime
import time
from typing import Dict, Optional
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleServerMonitor:
    def __init__(self):
        # Configurações InfluxDB
        self.client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.bucket = os.getenv("INFLUXDB_BUCKET")
        
        # Limiares fixos baseados em horários
        self.thresholds = {
            'peak_hours': range(9, 18),
            'upload': {
                'peak': {
                    'optimal': 0.75,
                    'warning': 0.50,
                    'critical': 0.25
                },
                'off_peak': {
                    'optimal': 0.85,
                    'warning': 0.60,
                    'critical': 0.35
                }
            },
            'latency': {
                'peak': {
                    'optimal': 30,   
                    'warning': 50,   
                    'critical': 100   
                },
                'off_peak': {
                    'optimal': 20,    
                    'warning': 40,    
                    'critical': 80    
                }
            }
        }

    def get_recent_data(self, minutes: int = 5) -> Optional[pd.DataFrame]:
        """Busca dados recentes do servidor"""
        query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{minutes}m)
                |> filter(fn: (r) => r["_measurement"] == "network_metrics")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query_data_frame(query)
            if result.empty:
                logger.warning("Sem dados recentes disponíveis")
                return None
            return result
        except Exception as e:
            logger.error(f"Erro ao buscar dados: {str(e)}")
            return None

    def calculate_averages(self, data: pd.DataFrame) -> Dict:
        """Calcula médias móveis simples para métricas chave"""
        return {
            'upload_speed': {
                'current': data['upload_speed'].iloc[-1],
                'avg_5min': data['upload_speed'].mean(),
                'std_5min': data['upload_speed'].std()
            },
            'latency': {
                'current': data['latency'].iloc[-1],
                'avg_5min': data['latency'].mean(),
                'std_5min': data['latency'].std()
            }
        }

    def detect_simple_anomalies(self, stats: Dict) -> bool:
        """Detecta anomalias usando regras simples baseadas em desvio padrão"""
        for metric in ['upload_speed', 'latency']:
            current = stats[metric]['current']
            mean = stats[metric]['avg_5min']
            std = stats[metric]['std_5min']
            
            # Se o valor atual estiver mais que 2 desvios padrão da média
            if abs(current - mean) > 2 * std:
                return True
        return False

    def analyze_server_health(self, current_data: pd.DataFrame, stats: Dict) -> Dict:
        """Analisa saúde do servidor usando regras simples"""
        current_hour = pd.to_datetime(current_data['_time'].iloc[-1]).hour
        is_peak = current_hour in self.thresholds['peak_hours']
        period = 'peak' if is_peak else 'off_peak'
        
        thresholds = {
            'upload': self.thresholds['upload'][period],
            'latency': self.thresholds['latency'][period]
        }
        
        # Calcula score de saúde
        health_score = 0.0
        current_upload = stats['upload_speed']['current']
        current_latency = stats['latency']['current']
        
        # Avalia upload (40% do peso)
        if current_upload >= thresholds['upload']['optimal']:
            health_score += 0.4
        elif current_upload >= thresholds['upload']['warning']:
            health_score += 0.2
            
        # Avalia latência (60% do peso)
        if current_latency <= thresholds['latency']['optimal']:
            health_score += 0.6
        elif current_latency <= thresholds['latency']['warning']:
            health_score += 0.3
            
        # Determina status
        if health_score >= 0.8:
            status = "optimal"
        elif health_score >= 0.5:
            status = "good"
        elif health_score >= 0.3:
            status = "warning"
        else:
            status = "critical"
            
        return {
            'status': status,
            'health_score': health_score,
            'is_peak_hour': is_peak
        }

    def monitor_and_analyze(self):
        """Monitora e analisa métricas do servidor"""
        try:
            recent_data = self.get_recent_data()
            if recent_data is None or recent_data.empty:
                return
                
            # Calcula estatísticas
            stats = self.calculate_averages(recent_data)
            
            # Detecta anomalias simples
            is_anomaly = self.detect_simple_anomalies(stats)
            
            # Analisa status
            health_analysis = self.analyze_server_health(recent_data, stats)
            
            # Salva no InfluxDB
            point = Point("server_analysis") \
                .field("current_upload", float(stats['upload_speed']['current'])) \
                .field("current_latency", float(stats['latency']['current'])) \
                .field("avg_upload_5min", float(stats['upload_speed']['avg_5min'])) \
                .field("avg_latency_5min", float(stats['latency']['avg_5min'])) \
                .field("health_status", health_analysis['status']) \
                .field("health_score", float(health_analysis['health_score'])) \
                .field("is_anomaly", int(is_anomaly)) \
                .field("is_peak_hour", int(health_analysis['is_peak_hour']))
            
            self.write_api.write(bucket=self.bucket, record=point)
            
            logger.info(
                f"Análise do servidor - Status: {health_analysis['status']}, "
                f"Score: {health_analysis['health_score']:.2f}, "
                f"Período: {'Pico' if health_analysis['is_peak_hour'] else 'Normal'}"
            )
            
        except Exception as e:
            logger.error(f"Erro ao processar análise: {str(e)}")

def main():
    logger.info("Iniciando Simple Server Monitor...")
    monitor = SimpleServerMonitor()
    
    try:
        while True:
            monitor.monitor_and_analyze()
            time.sleep(5)  # Intervalo de 5 segundos por análise
            
    except KeyboardInterrupt:
        logger.info("Encerrando Simple Server Monitor...")
    except Exception as e:
        logger.error(f"Erro no loop principal: {str(e)}")
    finally:
        monitor.client.close()

if __name__ == "__main__":
    main()