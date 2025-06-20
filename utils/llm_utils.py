import json
import streamlit as st
from snowflake.cortex import Complete, CompleteOptions
from utils.snowflake_utils import session


def _build_refine_prompt(raw_question: str, chat_history: str) -> str:
    """
    Construct a prompt for refining user questions using chat history.
    """
    
    system = """
    You are a query refiner.
    
    Given the recent chat history and a user input, produce a clear, focused question that preserves the user's intent.
    1. If the input is already a question, clean it up with the necessary context from the chat history if it's relevant.
    2. If the input is a problem statement or request for help, rewrite it as a question that directly asks how to solve or troubleshoot the issue (e.g., “How can I […]?”).
    3. Preserve the original meaning and keywords; do not add new information.
    
    Output ONLY the rewritten question, ending with a question mark. — no extra comments and no follow-up questions.
    """
    return "\n".join([
        "[SYSTEM]",
        system,
        "[/SYSTEM]",
        "[HISTORY]",
        chat_history,
        "[/HISTORY]",
        "[ORIGINAL_QUESTION]",
        raw_question,
        "[/ORIGINAL_QUESTION]"
    ])


def refine_question(raw_question: str, model_name: str, num_history: int, temperature: float, max_tokens: int) -> str:
    """
    Optionally rewrite the user's question for clarity and focus.
    """
    
    if len(st.session_state.messages) < 2:
        return raw_question

    hist = st.session_state.messages[-num_history:]
    hist_json = json.dumps(hist)
    prompt = _build_refine_prompt(raw_question, hist_json)
    opts = CompleteOptions({
        "temperature": temperature,
        "max_tokens": max_tokens
    })
    try:
        return Complete(
            model_name,
            prompt,
            options=opts,
            session=session
        ).strip()
    except Exception as e:
        st.error(f"Refine error: {e}")
        return raw_question


def _build_invoice_prompt(context_json: str, question: str, chat_history: str = None) -> str:
    """
    Build a structured prompt for answering invoice questions using provided context.
    """
    
    system = """
    You are an invoice assistant.
    Answer the user's question using ONLY the data in the JSON context below. Be concise and factual.  
    Output must be valid Markdown.
    
    When you need to return multiple discrete pieces of information, format it as a Markdown list:
    - Always put a blank line before and after the list.
    - Start each bullet with `- ` (dash + space).
    
    Otherwise, respond in normal prose.
    
    If you cannot answer from the context, say “I don't know.”
    """
    parts = ["[SYSTEM]", system, "[/SYSTEM]", f"[CONTEXT]\n{context_json}\n[/CONTEXT]"]
    if chat_history:
        parts += [f"[HISTORY]\n{chat_history}\n[/HISTORY]"]
    parts += ["QUESTION:", question, "ANSWER:"]
    return "\n".join(parts)


def get_invoice_answer(question: str, context_chunks: list, model_name: str, max_tokens: int, temperature: float, chat_history: list = None) -> str:
    """
    Call the LLM to generate an answer for the invoice question.

    Constructs the prompt, invokes the completion API, and returns text.
    """
    
    context_json = json.dumps(context_chunks)
    history_json = json.dumps(chat_history) if chat_history else None
    prompt = _build_invoice_prompt(context_json, question, history_json)
    options = CompleteOptions({
        "max_tokens": max_tokens,
        "temperature": temperature
    })
    try:
        return Complete(model_name, prompt, options=options, session=session)
    except Exception as e:
        return f"Error: {e}"