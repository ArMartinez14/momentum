#!/bin/bash

# Script para ejecutar tests E2E de App Asesorías

echo "🚀 Configurando tests E2E para App Asesorías..."

# Verificar que estamos en el directorio correcto
if [ ! -f "appasesoria.py" ]; then
    echo "❌ Error: No se encontró appasesoria.py. Ejecuta desde el directorio raíz del proyecto."
    exit 1
fi

# Crear directorio de tests si no existe
mkdir -p tests

# Instalar dependencias de testing
echo "📦 Instalando dependencias de testing..."
pip install -r tests/requirements.txt

# Instalar navegadores de Playwright
echo "🌐 Instalando navegadores de Playwright..."
playwright install

# Crear secrets de prueba si no existen
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "🔐 Creando secrets de prueba..."
    mkdir -p .streamlit
    cat > .streamlit/secrets.toml << 'EOF'
[secrets]
FIREBASE_CREDENTIALS = '''
{
  "type": "service_account",
  "project_id": "test-project",
  "private_key_id": "test-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nMOCK_KEY\\n-----END PRIVATE KEY-----\\n",
  "client_email": "test@test-project.iam.gserviceaccount.com",
  "client_id": "test-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com"
}
'''
EOF
fi

# Verificar si Streamlit está ejecutándose
if ! curl -s http://localhost:8501 > /dev/null; then
    echo "⚠️  Streamlit no está ejecutándose en localhost:8501"
    echo "   Inicia la app con: streamlit run appasesoria.py"
    echo "   Luego ejecuta este script nuevamente."
    exit 1
fi

echo "✅ Streamlit detectado en localhost:8501"

# Ejecutar tests
echo "🧪 Ejecutando tests E2E..."
pytest tests/test_soft_login_e2e.py -v --tb=short

echo "✨ Tests completados!"