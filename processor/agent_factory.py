import streamlit as st
from processor.agent import ConfigurationValidationAgent

@st.cache_resource
def get_validation_agent():
    return ConfigurationValidationAgent()
