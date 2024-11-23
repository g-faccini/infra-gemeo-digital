import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import time

# Configuração da página
st.set_page_config(
    page_title="Dashboard de Monitoramento de Rede",
    layout="wide"
)

# Configuração do cliente InfluxDB
@st.cache_resource
def get_client():
    return influxdb_client.InfluxDBClient(
        url=os.getenv('INFLUXDB_URL'),
        token=os.getenv('INFLUXDB_TOKEN'),
        org=os.getenv('INFLUXDB_ORG')
    )

def get_data(time_range):
    client = get_client()
    query_api = client.query_api()
    
    # Query para buscar dados
    query = f'''
    from(bucket: "{os.getenv('INFLUXDB_BUCKET')}")
        |> range(start: -{time_range})
        |> filter(fn: (r) => r["_measurement"] == "network_metrics")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    
    result = query_api.query_data_frame(query)
    if len(result) == 0:
        return pd.DataFrame()
    
    # Limpa e prepara o DataFrame
    df = result.drop(columns=['result', 'table', '_measurement', '_start', '_stop'])
    df = df.rename(columns={'_time': 'time'})
    
    # Calcula a taxa de pacotes por segundo
    df['packets_sent_rate'] = df['packets_sent'].diff() / df['time'].diff().dt.total_seconds()
    df['packets_recv_rate'] = df['packets_recv'].diff() / df['time'].diff().dt.total_seconds()
    
    return df

def create_speed_chart(df):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['download_speed'],
                  name="Download Speed", line=dict(color="#2ecc71")),
        secondary_y=False,
    )
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['upload_speed'],
                  name="Upload Speed", line=dict(color="#3498db")),
        secondary_y=False,
    )
    
    fig.update_layout(
        title="Network Speed Over Time",
        yaxis_title="Speed (Mbps)",
        height=400
    )
    
    return fig

def create_packet_rates_chart(df):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['packets_sent_rate'],
                  name="Packets Sent/s", line=dict(color="#e74c3c")),
        secondary_y=False,
    )
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['packets_recv_rate'],
                  name="Packets Received/s", line=dict(color="#9b59b6")),
        secondary_y=False,
    )
    
    fig.update_layout(
        title="Network Packet Rates",
        yaxis_title="Packets per Second",
        height=400
    )
    
    return fig

def create_errors_chart(df):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['errors_in'],
                  name="Errors In", line=dict(color="#f1c40f")),
        secondary_y=False,
    )
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['errors_out'],
                  name="Errors Out", line=dict(color="#e67e22")),
        secondary_y=False,
    )
    
    fig.update_layout(
        title="Network Errors Over Time",
        yaxis_title="Error Count",
        height=400
    )
    
    return fig

def create_latency_chart(df):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(x=df['time'], y=df['latency'],
                  name="Latency", line=dict(color="#dcae96")),
        secondary_y=False,
    )
    
    fig.update_layout(
        title="Latency over time",
        yaxis_title="Latency",
        height=400
    )
    
    return fig

def main():
    st.title(" Dashboard de Monitoramento de Rede")
    
    # Controles na sidebar
    st.sidebar.title("Configurações")
    
    # Seletor de intervalo de tempo
    time_ranges = {
        "Última hora": "1h",
        "Últimas 6 horas": "6h",
        "Último dia": "24h",
        "Última semana": "7d"
    }
    
    selected_range = st.sidebar.selectbox(
        "Selecione o intervalo de tempo",
        options=list(time_ranges.keys())
    )
    
    # Controle de atualização automática
    auto_refresh = st.sidebar.checkbox("Atualização automática", value=True)
    refresh_interval = st.sidebar.slider(
        "Intervalo de atualização (segundos)",
        min_value=5,
        max_value=60,
        value=10
    )
    
    # Contador de tempo para próxima atualização
    if auto_refresh:
        placeholder = st.sidebar.empty()
        
    # Container principal para os dados
    main_container = st.container()
    
    while True:
        with main_container:
            # Obtém os dados
            df = get_data(time_ranges[selected_range])
            
            if df.empty:
                st.warning("Sem dados disponíveis para o período selecionado.")
                if auto_refresh:
                    time.sleep(refresh_interval)
                    st.rerun()
                return
            
            # Métricas principais
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric(
                    "Download Speed",
                    f"{df['download_speed'].iloc[-1]:.2f} Mbps",
                    f"{df['download_speed'].iloc[-1] - df['download_speed'].iloc[-2]:.2f} Mbps"
                )
            
            with col2:
                st.metric(
                    "Upload Speed",
                    f"{df['upload_speed'].iloc[-1]:.2f} Mbps",
                    f"{df['upload_speed'].iloc[-1] - df['upload_speed'].iloc[-2]:.2f} Mbps"
                )
            
            with col3:
                st.metric(
                    "Current Packet Rate (Send)",
                    f"{df['packets_sent_rate'].iloc[-1]:.0f}/s",
                    f"{df['packets_sent_rate'].iloc[-1] - df['packets_sent_rate'].iloc[-2]:.0f}/s"
                )
            
            with col4:
                st.metric(
                    "Current Packet Rate (Recv)",
                    f"{df['packets_recv_rate'].iloc[-1]:.0f}/s",
                    f"{df['packets_recv_rate'].iloc[-1] - df['packets_recv_rate'].iloc[-2]:.0f}/s"
                )
            with col5:
                st.metric(
                    "Current Latency",
                    f"{df['latency'].iloc[-1]:.0f}ms",
                    f"{df['latency'].iloc[-1] - df['latency'].iloc[-2]:.0f}ms"
                )
            
            # Gráficos
            st.plotly_chart(create_speed_chart(df), use_container_width=True)
            st.plotly_chart(create_latency_chart(df), use_container_width=True)
            st.plotly_chart(create_packet_rates_chart(df), use_container_width=True)
            st.plotly_chart(create_errors_chart(df), use_container_width=True)
            
            # Tabela de dados recentes
            with st.expander("Ver dados recentes"):
                display_df = df[['time', 'download_speed', 'upload_speed', 
                                'packets_sent_rate', 'packets_recv_rate', 
                                'errors_in', 'errors_out','latency']].copy()
                
                st.dataframe(
                    display_df.sort_values('time', ascending=False)
                    .head(100)
                    .style.format({
                        'download_speed': '{:.2f}',
                        'upload_speed': '{:.2f}',
                        'packets_sent_rate': '{:.0f}',
                        'packets_recv_rate': '{:.0f}',
                        'errors_in': '{:.0f}',
                        'errors_out': '{:.0f}',
                        'latency': '{:.1f}'
                    })
                )
        
        if not auto_refresh:
            break
            
        # Atualiza o contador
        for remaining in range(refresh_interval, 0, -1):
            placeholder.text(f"Próxima atualização em {remaining} segundos")
            time.sleep(1)
            
        st.rerun()

if __name__ == "__main__":
    main()