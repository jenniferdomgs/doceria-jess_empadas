# Dockerfile
FROM python:3.12-slim

# Definindo o diretório de trabalho
WORKDIR /app

# Copiando os arquivos de dependências
COPY requirements.txt .

# Instalando as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiando os arquivos da aplicação
COPY . .
COPY . /app

# Expondo a porta da aplicação Flask
EXPOSE 5000

# Comando para iniciar a aplicação
CMD ["python", "app.py"]

