import tempfile, os, requests, json
from dotenv import load_dotenv
from groq import Groq
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import fitz  # pymupdf
import plotly.graph_objects as go
import streamlit as st

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def transcrire(audio_path):
    with open(audio_path, "rb") as f:
        res = client.audio.transcriptions.create(
            file=(audio_path, f.read()),
            model="whisper-large-v3", language="fr"
        )
    return res.text

def extraire_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

def fetch_pubmed(query, n=3):
    search = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db":"pubmed","term":query,"retmax":n,"retmode":"json"}).json()
    ids = search["esearchresult"]["idlist"]
    if not ids:
        return ""
    return requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={"db":"pubmed","id":",".join(ids),"rettype":"abstract","retmode":"text"}).text

def decouper_chunks(texte, taille=100):
    mots = texte.split()
    return [" ".join(mots[i:i+taille]) for i in range(0, len(mots), taille)]

def construire_rag(pdf_text, guidelines_txt):
    ef = SentenceTransformerEmbeddingFunction("paraphrase-multilingual-MiniLM-L12-v2")
    col = chromadb.Client().create_collection("rag", embedding_function=ef)
    docs = decouper_chunks(pdf_text)
    if guidelines_txt:
        docs.extend(decouper_chunks(guidelines_txt))
    col.add(documents=docs, ids=[str(i) for i in range(len(docs))])
    return col

def recuperer_contexte(collection, query, n=5):
    res = collection.query(query_texts=[query], n_results=n)
    return "\n\n".join(res["documents"][0])



def analyser_fct(transcript, contexte):
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": (
                "Tu es un assistant médical. Produis 3 sections :\n"
                "1. **Diagnostic structuré**\n"
                "2. **Résumé clair pour le patient** (sans jargon)\n"
                "3. **Plan d'action personnalisé**"
            )},
            {"role": "user", "content": (
                f"=== CONTEXTE MÉDICAL (RAG) ===\n{contexte}\n\n"
                f"=== TRANSCRIPTION ===\n{transcript}"
            )}
        ], temperature=0.3
    )
    return res.choices[0].message.content

def extraire_donnees_suivi(pdf_text):
    
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": """
Tu es un extracteur de données médicales. Extrais les données de suivi du dossier patient.
Réponds UNIQUEMENT en JSON valide, sans texte autour, avec ce format exact :
{
  "tension": [{"date": "2024-01", "systolique": 140, "diastolique": 90}, ...],
  "hba1c": [{"date": "2024-01", "valeur": 8.2}, ...],
  "poids": [{"date": "2024-01", "valeur": 85}, ...],
  "medicaments": [{"nom": "Metformine 500mg", "frequence": "2x/jour", "depuis": "2022-01"}, ...]
}
Si une donnée est absente du dossier, mets un tableau vide [].
"""},
            {"role": "user", "content": f"Dossier patient :\n{pdf_text}"}
        ], temperature=0
    )
    raw = res.choices[0].message.content
    
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
def afficher_graphiques(data):
    if data.get("tension"):
        st.subheader("🫀 Tension artérielle")
        tension_clean = [
            d for d in data["tension"]
            if d.get("systolique") is not None and d.get("diastolique") is not None
        ]
        if not tension_clean:
            st.info("Données de tension insuffisantes.")
        else:
            dates = [d["date"] for d in tension_clean]
            sys_  = [int(d["systolique"]) for d in tension_clean]
            dia_  = [int(d["diastolique"]) for d in tension_clean]
            couleurs_sys = ["red" if v > 130 else "green" for v in sys_]
            couleurs_dia = ["red" if v > 80 else "green" for v in dia_]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=sys_, name="Systolique",
                line=dict(color="#e74c3c", width=2), mode="lines+markers",
                marker=dict(color=couleurs_sys, size=10)))
            fig.add_trace(go.Scatter(x=dates, y=dia_, name="Diastolique",
                line=dict(color="#3498db", width=2), mode="lines+markers",
                marker=dict(color=couleurs_dia, size=10)))
            fig.add_hline(y=130, line_dash="dash", line_color="orange",
                annotation_text="⚠️ Seuil HAS systolique (130)")
            fig.add_hline(y=80, line_dash="dash", line_color="orange",
                annotation_text="⚠️ Seuil HAS diastolique (80)")
            fig.update_layout(yaxis_title="mmHg", height=350)
            st.plotly_chart(fig, use_container_width=True)
            if sys_[-1] > 130 or dia_[-1] > 80:
                st.error(f"🚨 Tension actuelle hors norme HAS : {sys_[-1]}/{dia_[-1]} mmHg")
            else:
                st.success(f"✅ Tension dans les normes : {sys_[-1]}/{dia_[-1]} mmHg")

    if data.get("hba1c"):
        st.subheader("🩸 HbA1c")
        hba1c_clean = [d for d in data["hba1c"] if d.get("valeur") is not None]
        if not hba1c_clean:
            st.info("Données HbA1c insuffisantes.")
        else:
            dates   = [d["date"] for d in hba1c_clean]
            valeurs = [float(d["valeur"]) for d in hba1c_clean]
            couleurs = ["red" if v > 7 else "green" for v in valeurs]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=valeurs, name="HbA1c",
                line=dict(color="#9b59b6", width=2), mode="lines+markers",
                marker=dict(color=couleurs, size=10)))
            fig.add_hline(y=7, line_dash="dash", line_color="orange",
                annotation_text="⚠️ Seuil HAS (7%)")
            fig.add_hrect(y0=7, y1=15, fillcolor="red", opacity=0.05,
                annotation_text="Zone à risque")
            fig.update_layout(yaxis_title="%", height=350)
            st.plotly_chart(fig, use_container_width=True)
            if valeurs[-1] > 7:
                st.error(f"🚨 HbA1c hors norme HAS : {valeurs[-1]}% (objectif < 7%)")
            else:
                st.success(f"✅ HbA1c dans les normes : {valeurs[-1]}%")

    if data.get("poids"):
        st.subheader("⚖️ Poids")
        poids_clean = [d for d in data["poids"] if d.get("valeur") is not None]
        if not poids_clean:
            st.info("Données de poids insuffisantes.")
        else:
            dates   = [d["date"] for d in poids_clean]
            valeurs = [float(d["valeur"]) for d in poids_clean]
            taille  = 1.75
            imcs    = [round(p / (taille ** 2), 1) for p in valeurs]
            couleurs = ["red" if imc > 25 else "green" for imc in imcs]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=dates, y=valeurs, name="Poids (kg)",
                marker_color=couleurs))
            fig.add_hline(y=taille**2 * 25, line_dash="dash", line_color="orange",
                annotation_text="⚠️ Seuil surpoids IMC 25")
            fig.add_hline(y=taille**2 * 30, line_dash="dash", line_color="red",
                annotation_text="🚨 Seuil obésité IMC 30")
            fig.update_layout(yaxis_title="kg", height=350)
            st.plotly_chart(fig, use_container_width=True)
            dernier_imc = imcs[-1]
            if dernier_imc > 30:
                st.error(f"🚨 Obésité : IMC {dernier_imc} (> 30)")
            elif dernier_imc > 25:
                st.warning(f"⚠️ Surpoids : IMC {dernier_imc} (> 25)")
            else:
                st.success(f"✅ IMC normal : {dernier_imc}")

    if data.get("medicaments"):
        st.subheader("💊 Médicaments actuels")
        for med in data["medicaments"]:
            if med.get("nom"):
                st.markdown(f"- **{med['nom']}** — {med.get('frequence','?')} *(depuis {med.get('depuis','?')})*")

PROMPTS_CHATBOT = {
    "🧑‍⚕️ Médecin": """Tu es un assistant médical expert. Tu as accès au dossier complet du patient.
Réponds de façon technique et précise. Cite les données chiffrées du dossier quand c'est pertinent.
Dossier patient : {contexte}""",

    "🙋 Patient": """Tu es un assistant de santé bienveillant qui aide un patient à comprendre sa santé.
Utilise un langage simple, rassurant, sans jargon médical.
Dossier du patient : {contexte}"""
}

def chat_response(messages, mode, contexte_patient, transcript):
    system = PROMPTS_CHATBOT[mode].format(contexte=contexte_patient[:3000]) + f"\n\nTranscription de la consultation du jour :\n{transcript}"
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.5
    )
    return res.choices[0].message.content

