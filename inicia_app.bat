@echo off
echo Ativando ambiente virtual...
call source\Scripts\activate.bat

echo Instalando dependências (caso necessário)...
pip install flask

echo Iniciando o aplicativo Flask...
python app.py

pause
