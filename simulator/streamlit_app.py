from __future__ import annotations

import asyncio
import threading
import time

import pandas as pd
import streamlit as st

from client_simulator import FleetSimulator
from config import SimulatorConfig


def _start_simulator(config: SimulatorConfig) -> None:
    simulator = FleetSimulator(config)
    st.session_state["simulator"] = simulator
    st.session_state["running"] = True

    def _runner() -> None:
        asyncio.run(simulator.run())
        st.session_state["running"] = False

    thread = threading.Thread(target=_runner, daemon=True)
    st.session_state["sim_thread"] = thread
    thread.start()


def _stop_simulator() -> None:
    simulator: FleetSimulator | None = st.session_state.get("simulator")
    if simulator is not None:
        simulator.stop()


st.set_page_config(page_title="Telemetry Simulator", layout="wide")
st.title("Minimal Fleet Simulator")

with st.sidebar:
    st.header("Config")
    ws_url = st.text_input("WS URL", value="ws://127.0.0.1:8000/ws")
    fleet_size = st.slider("Fleet size", min_value=1, max_value=500, value=100, step=1)
    drop_probability = st.slider(
        "Drop probability per tick",
        min_value=0.0,
        max_value=0.5,
        value=0.05,
        step=0.01,
    )
    tick_seconds = st.slider("Tick seconds", min_value=0.2, max_value=5.0, value=1.0, step=0.1)
    reconnect_delay_seconds = st.slider(
        "Reconnect delay (seconds)", min_value=0.2, max_value=5.0, value=1.5, step=0.1
    )
    bulk_sync_batch_size = st.slider(
        "Bulk sync batch size", min_value=10, max_value=1000, value=100, step=10
    )

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("Start", use_container_width=True):
            if not st.session_state.get("running", False):
                _start_simulator(
                    SimulatorConfig(
                        ws_url=ws_url,
                        fleet_size=fleet_size,
                        drop_probability=drop_probability,
                        tick_seconds=tick_seconds,
                        reconnect_delay_seconds=reconnect_delay_seconds,
                        bulk_sync_batch_size=bulk_sync_batch_size,
                    )
                )
    with col_stop:
        if st.button("Stop", use_container_width=True):
            _stop_simulator()

simulator: FleetSimulator | None = st.session_state.get("simulator")
running = st.session_state.get("running", False)
st.caption(f"Status: {'running' if running else 'stopped'}")

if simulator is not None:
    totals = simulator.metrics.snapshot()
else:
    totals = {
        "sent_telemetry": 0,
        "queued": 0,
        "bulk_synced": 0,
        "drops": 0,
        "reconnects": 0,
        "acks": 0,
        "errors": 0,
    }

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sent telemetry", totals["sent_telemetry"])
c2.metric("Queued", totals["queued"])
c3.metric("Bulk synced", totals["bulk_synced"])
c4.metric("Drops", totals["drops"])

c5, c6, c7 = st.columns(3)
c5.metric("Reconnects", totals["reconnects"])
c6.metric("ACKs", totals["acks"])
c7.metric("Errors", totals["errors"])

if simulator is not None:
    history = simulator.metrics.history()
    if history:
        df = pd.DataFrame(history)
        st.line_chart(df[["queued", "bulk_synced", "drops"]])

if running:
    time.sleep(1.0)
    st.rerun()
