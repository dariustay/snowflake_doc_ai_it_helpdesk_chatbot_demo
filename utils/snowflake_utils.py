import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.core import Root


@st.cache_resource
def _init_snowflake():
    """
    Initialize and return a Snowpark session and Root object.
    """
    
    sess = get_active_session()
    return sess, Root(sess)

# Initialize session
session, root = _init_snowflake()