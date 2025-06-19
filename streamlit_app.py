import json
import streamlit as st
import pypdfium2 as pdfium
from typing import Any, Dict, List
from utils.snowflake_utils import session, root
from utils.llm_utils import get_invoice_answer, refine_question
from utils.search_utils import query_cortex_search_service


# === Configuration Constants ===

MODEL = "claude-3-5-sonnet"

REFINE_TEMPERATURE = 0.0
REFINE_MAX_TOKENS = 500

SUMMARY_TEMPERATURE = 0.0
SUMMARY_MAX_TOKENS = 750


# === Helper Functions ===

@st.cache_data(show_spinner=False)
def load_service_metadata() -> List[Dict[str, Any]]:
    """
    Fetch and cache metadata (names and search columns) for all Cortex search services.
    """
    
    rows = session.sql("SHOW CORTEX SEARCH SERVICES").collect()
    metas: List[Dict[str, Any]] = []
    for s in rows:
        name = s["name"]
        desc = session.sql(f"DESC CORTEX SEARCH SERVICE {name}").collect()
        search_col = desc[0]["search_column"] if desc else None
        metas.append({"name": name, "search_column": search_col})
    return metas


def load_config() -> Dict[str, Any]:
    """
    Render sidebar controls and assemble configuration parameters.
    """
    
    # Load service metadata once
    if "service_metadata" not in st.session_state:
        st.session_state.service_metadata = load_service_metadata()

    # Search configuration UI
    with st.sidebar.expander("🔍 Search Configuration", expanded=False):
        svc_names = [m["name"] for m in st.session_state.service_metadata]
        selected_service = st.selectbox("Service:", svc_names)
        num_retrieved_chunks = st.number_input(
            "Chunks to retrieve:", min_value=1, max_value=10, value=3
        )

    # Chat and LLM settings UI
    with st.sidebar.expander("💬 Chat Settings", expanded=False):
        num_chat_messages = st.number_input(
            "History turns:", min_value=1, max_value=10, value=5
        )

    st.sidebar.markdown("---")
    
    # Clear conversation button
    if st.sidebar.button("Clear conversation"):
        st.session_state.clear_conversation = True

    # Return assembled config
    return {
        "selected_service": selected_service,
        "num_retrieved_chunks": num_retrieved_chunks,
        "num_chat_messages": num_chat_messages,
        "refine_temperature": REFINE_TEMPERATURE,
        "refine_max_tokens": REFINE_MAX_TOKENS,
        "summary_temperature": SUMMARY_TEMPERATURE,
        "summary_max_tokens": SUMMARY_MAX_TOKENS,
    }


def init_messages() -> None:
    """
    Initialize or reset the chat message history stored in session state.
    """
    
    if st.session_state.get("clear_conversation"):
        st.session_state.messages = []
        st.session_state.clear_conversation = False
        
    if "messages" not in st.session_state:
        st.session_state.messages = []


def display_pdf_page(key: str):
    """
    Render the first page of the PDF in session state.
    """
    
    pdf = st.session_state[key]
    page = pdf.get_page(0)
    bitmap = page.render(scale=2)
    st.image(bitmap.to_pil(), use_container_width=True)
    page.close()


def main_chat_loop(config: Dict[str, Any], model: str) -> None:
    """
    Main interaction loop: render past messages, accept new questions,
    refine them, retrieve context, generate answers, and display results.
    """
    
    # Render existing chat messages
    for msg in st.session_state.messages:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    # Accept user input
    if user_q := st.chat_input("Type your question here..."):
        
        # Save raw input
        st.session_state.messages.append({"role": "user", "content": user_q})

        # Refine the question for better LLM performance
        rewritten_q = refine_question(
            raw_question=user_q,
            model_name=model,
            num_history=config['num_chat_messages'],
            temperature=config['refine_temperature'],
            max_tokens=config['refine_max_tokens']
        )

        # Retrieve context chunks via Cortex Search
        chunks = query_cortex_search_service(
            rewritten_q,
            service=config['selected_service'],
            limit=config['num_retrieved_chunks'],
            metadata=st.session_state.service_metadata,
        )
        st.session_state.last_context_json = json.dumps(chunks)

        # Display user message and optional refinement
        with st.chat_message("user"):
            st.markdown(user_q)
            if rewritten_q != user_q:
                st.markdown(f"**Refined question:** {rewritten_q}")

        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Generating response…"):
                answer = get_invoice_answer(
                    question=rewritten_q,
                    context_chunks=chunks,
                    model_name=model,
                    max_tokens=config['summary_max_tokens'],
                    temperature=config['summary_temperature'],
                    chat_history=st.session_state.messages[-config['num_chat_messages']:]
                )

                # For debugging: Uncomment if the text format looks weird
                # st.sidebar.markdown("#### Raw LLM response")
                # st.sidebar.code(answer, language="text")
                
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.markdown(answer)

        # Show raw search results for transparency
        st.markdown("###### 🔍 Search Results")
        if chunks:
            for idx, c in enumerate(chunks, start=1):
                with st.expander(f"Result {idx}: {c['file']}"):
                    
                    # Load PDF once per file
                    key = f"pdf_doc_{c['file']}"
                    if key not in st.session_state:
                        stage_ref = f"@{session.get_current_database()}.{session.get_current_schema()}.DOC_AI_STAGE/{c['file']}"
                        raw_bytes = session.file.get_stream(stage_ref).read()
                        st.session_state[key] = pdfium.PdfDocument(raw_bytes)
                    
                    # Display only first page
                    display_pdf_page(key)
        else:
            st.info("No search results found.")


# === Streamlit App ===

def main() -> None:
    """
    Entry point for the Streamlit app: set up state, config and kick off the chat loop.
    """
    
    init_messages()
    config = load_config()
    st.title("IT HelpDesk Chatbot")
    st.write("💬 Ask questions about IT-related issues powered by Cortex Search.")
    st.write("")
    main_chat_loop(config, model=MODEL)


if __name__ == "__main__":
    main()