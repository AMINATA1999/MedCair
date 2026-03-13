import streamlit as st
from analyzer import *
import tempfile, os
st.set_page_config(page_title="MedClair", page_icon="🩺", layout="wide")
st.title("🩺 MedClair")

with st.sidebar:
    st.header("📁 Documents")
    audio_file   = st.file_uploader("🎙️ Audio consultation", type=["mp3","wav","m4a"])
    patient_pdf  = st.file_uploader("📄 Dossier patient (PDF)", type=["pdf"])
    pubmed_query = st.text_input("🔬 Guidelines PubMed")
    go = st.button("🚀 Analyser", type="primary", use_container_width=True)

if "resultat"        not in st.session_state: st.session_state.resultat = None
if "transcript"      not in st.session_state: st.session_state.transcript = None
if "pdf_text"        not in st.session_state: st.session_state.pdf_text = None
if "contexte_rag"    not in st.session_state: st.session_state.contexte_rag = None
if "donnees_suivi"   not in st.session_state: st.session_state.donnees_suivi = None
if "chat_history"    not in st.session_state: st.session_state.chat_history = []


if go:
    if not audio_file :
        st.sidebar.error("Audio requis"); st.stop()
        

    with tempfile.NamedTemporaryFile(delete=False, suffix="."+audio_file.name.split(".")[-1]) as f:
        f.write(audio_file.read()); audio_path = f.name

    with st.sidebar:
        with st.spinner("Transcription..."):
            st.session_state.transcript = transcrire(audio_path)

        if patient_pdf:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                f.write(patient_pdf.read()); pdf_path = f.name
            with st.spinner("Lecture PDF..."):
                st.session_state.pdf_text = extraire_pdf(pdf_path)
            os.unlink(pdf_path)
        else:
            st.session_state.pdf_text = ""

        guidelines = fetch_pubmed(pubmed_query) if pubmed_query else ""

        with st.spinner("RAG..."):
            if st.session_state.pdf_text or guidelines:
                col = construire_rag(st.session_state.pdf_text, guidelines)
                st.session_state.contexte_rag = recuperer_contexte(col, st.session_state.transcript)
            else:
                st.session_state.contexte_rag = st.session_state.transcript
                
       

        with st.spinner("Analyse LLM..."):
            st.session_state.resultat = analyser_fct(st.session_state.transcript,
                                                    st.session_state.contexte_rag)
        with st.spinner("Extraction données suivi..."):
            st.session_state.donnees_suivi = extraire_donnees_suivi(st.session_state.pdf_text)

        st.session_state.chat_history = []
        st.success("✅ Analyse terminée !")
        os.unlink(audio_path)


tab1, tab2, tab3 = st.tabs(["📋 Analyse", "📊 Suivi", "💬 Chatbot"])

with tab1:
    if st.session_state.transcript:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📝 Transcription")
            st.text_area("", value=st.session_state.transcript, height=250)
        with col2:
            if st.session_state.contexte_rag:
                with st.expander("🔍 Chunks RAG sélectionnés"):
                    st.text(st.session_state.contexte_rag)
        st.divider()
        #st.subheader("✅ Résultats")
        st.markdown(st.session_state.resultat)
        st.download_button("📥 Télécharger", data=st.session_state.resultat,
                           file_name="plan_patient.txt")
    else:
        st.info("⬅️ Importez les fichiers dans la sidebar et cliquez sur Analyser.")

with tab2:
    if st.session_state.donnees_suivi:
        st.subheader("📊 Suivi du patient dans le temps")
        afficher_graphiques(st.session_state.donnees_suivi)
    else:
        st.info("⬅️ Lancez d'abord une analyse.")


with tab3:
    #if not st.session_state.pdf_text:
    if not st.session_state.get("resultat"):
        st.info("⬅️ Lancez d'abord une analyse.")
    else:
        mode = st.radio("Mode", ["🙋 Patient", "🧑‍⚕️ Médecin"], horizontal=True)

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Posez votre question..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("..."):
                    
                    messages_llm = [{"role": m["role"], "content": m["content"]}
                                    for m in st.session_state.chat_history]
                    reponse = chat_response(messages_llm, mode, st.session_state.pdf_text, st.session_state.transcript)
                st.markdown(reponse)

            st.session_state.chat_history.append({"role": "assistant", "content": reponse})
            
            