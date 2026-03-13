MedAssist — Guide d’exécution
1. Cloner le dépôt
git clone https://github.com/ton_nom/MedAssist.git
cd MedAssist
2. Installer les dépendances
pip install -r requirements.txt
3. Créer le fichier .env
Crée un fichier .env à la racine du projet avec vos clés API :
GROQ_API_KEY=ta_cle_api_ici

4. Lancer l’application
streamlit run app.py
L’application s’ouvrira dans votre navigateur à l’adresse : http://localhost:8501
Vous pourrez uploader un fichier audio et un PDF patient, puis cliquer sur Analyser pour générer le plan patient.
5. Utilisation rapide
Charger un audio de consultation (MP3, WAV, M4A)
Charger un PDF patient
Optionnel : entrer un mot-clé pour PubMed
Cliquer sur Analyser
Explorer les résultats et consulter le suivi graphique
Poser des questions via le chatbot
