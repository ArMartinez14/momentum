# app_login_test.py
import streamlit as st
st.set_page_config(page_title="Smoke Login", layout="wide")

from soft_login_full import soft_login_test_ui

# 👉 Ejecuta el flujo de prueba definido en soft_login_full.py
soft_login_test_ui()
