from flask import Flask, render_template, request, url_for, redirect, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import User
import psycopg2
import os
import bcrypt
from models import User
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

app = Flask(__name__, static_folder='static')

app.secret_key = os.getenv('SECRET_KEY', 'U2T4C6')  

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    connection = conexaodb()
    if connection is None:
        return None
    
    cursor = connection.cursor()
    cursor.execute("SELECT cpf, 'usuario' FROM usuario WHERE cpf = %s UNION SELECT cnpj, 'fornecedor' FROM fornecedor WHERE cnpj = %s", (user_id, user_id))
    user = cursor.fetchone()
    
    cursor.close()
    connection.close()

    if user:
        return User(user[0], user[1])
    return None

def conexaodb():
    try:
        connection = psycopg2.connect(os.getenv('DATABASE_URL'))
        return connection
    except Exception as e:
        print(f"Erro na conexão com o banco de dados: {e}")
        return None

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ('http', 'https') and
        ref_url.netloc == test_url.netloc
    )

@app.route('/', methods=['GET'])
def home():
    termo = request.args.get('q', '').strip()  

    connection = conexaodb()
    if connection is None:
        return "Erro ao conectar ao banco de dados."

    cursor = connection.cursor()

    query = """
        SELECT produto.nome, imagem.urlImagem, produto.codproduto, produto.valor, produto.vencimento, produto.descricao, produto.nomeCategoria
        FROM produto
        JOIN imagem ON produto.codproduto = imagem.codProduto
    """
    params = ()
    if termo:
        query += " WHERE LOWER(produto.nome) LIKE %s"
        params = (f"%{termo.lower()}%",)
    
    cursor.execute(query, params)
    resultados = cursor.fetchall()

    # converte para lista de dicionários e calcula validade_proxima
    produtos = []
    hoje = datetime.today().date()
    alerta_dias = 5 

    for r in resultados:
        vencimento = r[4]
        validade_proxima = False
        if vencimento:
            if isinstance(vencimento, str):
                vencimento = datetime.strptime(vencimento, "%Y-%m-%d").date()
            validade_proxima = vencimento <= hoje + timedelta(days=alerta_dias)
        
        produtos.append({
            'nome': r[0],
            'imagem': r[1],
            'codproduto': r[2],
            'valor': r[3],
            'validade': vencimento.strftime("%d/%m/%Y") if vencimento else '',
            'descricao': r[5],
            'categoria': r[6],
            'validade_proxima': validade_proxima
        })

    # seleciona os 3 mais vendidos (alterar p/ vendas reais)
    cursor.execute("""
        SELECT produto.nome, imagem.urlImagem, produto.codproduto, produto.valor, produto.vencimento, produto.descricao, produto.nomeCategoria
        FROM produto
        JOIN imagem ON produto.codproduto = imagem.codProduto
        ORDER BY produto.valor DESC
        LIMIT 3
    """)
    mais_vendidos_raw = cursor.fetchall()
    mais_vendidos = []
    for r in mais_vendidos_raw:
        mais_vendidos.append({
            'nome': r[0],
            'imagem': r[1],
            'codproduto': r[2],
            'valor': r[3],
            'validade': r[4].strftime("%d/%m/%Y") if r[4] else '',
            'descricao': r[5],
            'categoria': r[6]
        })

    doces = [p for p in produtos if p['categoria'].lower() == 'doces']
    salgados = [p for p in produtos if p['categoria'].lower() == 'salgados']

    cursor.close()
    connection.close()

    tipo_usuario = current_user.user_type if current_user.is_authenticated else None  

    return render_template('home.html', 
                           produtos=produtos, 
                           tipo_usuario=tipo_usuario, 
                           termo_pesquisa=termo,
                           mais_vendidos=mais_vendidos,
                           doces=doces,
                           salgados=salgados)


@app.route('/produto/<string:id>', methods=['GET'])
def produto_detalhes(id):
    connection = conexaodb()
    if connection is None:
        return "Erro ao conectar ao banco de dados."

    cursor = connection.cursor()
    cursor.execute("""
        SELECT produto.nome, produto.descricao, produto.valor, imagem.urlImagem, produto.codproduto
        FROM produto
        LEFT JOIN imagem ON produto.codproduto = imagem.codProduto
        WHERE produto.codproduto = %s
        LIMIT 1
    """, (id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()

    if not row:
        abort(404)

    produto = {
        'nome': row[0],
        'descricao': row[1],
        'valor': row[2],
        'imagem': row[3],
        'codproduto': row[4]
    }

    return render_template('produto.html', produto=produto)


@app.route('/carrinho', methods=['POST'])
@login_required
def carrinho():
    return render_template('carrinho.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_data = request.form.get('login')
        senha = request.form.get('senha')

        if login_data.isdigit() is False:
            login_data_normalizado = ''.join(filter(str.isdigit, login_data))
        else:
            login_data_normalizado = login_data

        connection = conexaodb()
        if connection is None:
            return "Erro ao conectar ao banco de dados."
        
        cursor = connection.cursor()

        cursor.execute("SELECT cpf, senha FROM usuario WHERE cpf = %s OR email = %s", 
                       (login_data_normalizado, login_data))
        user = cursor.fetchone()

        if user and bcrypt.checkpw(senha.encode('utf-8'), user[1].encode('utf-8')):
            cursor.close()
            connection.close()
            login_user(User(user[0], 'usuario'))

            next_page = request.args.get('next')
            if not is_safe_url(next_page):
                return abort(400)
            return redirect(next_page or url_for('home'))

        cursor.execute("SELECT cnpj, senha FROM fornecedor WHERE cnpj = %s OR email = %s", 
                       (login_data_normalizado, login_data))
        fornecedor = cursor.fetchone()

        if fornecedor and bcrypt.checkpw(senha.encode('utf-8'), fornecedor[1].encode('utf-8')):
            cursor.close()
            connection.close()
            login_user(User(fornecedor[0], 'fornecedor'))

            next_page = request.args.get('next')
            if not is_safe_url(next_page):
                return abort(400)
            return redirect(next_page or url_for('home'))

        cursor.close()
        connection.close()
        return render_template('login.html', error="⚠️ Credenciais inválidas. Tente novamente!")

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        cpf = request.form.get('cpf')
        nome = request.form.get('nome')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        senha = request.form.get('senha')

        hashed_senha = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        connection = conexaodb()
        if connection is None:
            return "Erro ao conectar ao banco de dados."
        
        cursor = connection.cursor()
        cursor.execute('INSERT INTO usuario (cpf, nome, telefone, email, senha) VALUES (%s, %s, %s, %s, %s)',
            (cpf, nome, telefone, email, hashed_senha))

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for('home'))
    return render_template('cadastroU.html')


@app.route('/cadastroFornecedor', methods=['GET', 'POST'])
@login_required
def cadastroFornecedor():
    if current_user.user_type != 'fornecedor':
        return "Acesso negado.", 403
    
    if request.method == 'POST':
        cnpj = request.form.get('cnpj')
        nome = request.form.get('nome')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        senha = request.form.get('senha')

        hashed_senha = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        connection = conexaodb()
        if connection is None:
            return "Erro ao conectar ao banco de dados."
        
        cursor = connection.cursor()
        cursor.execute('INSERT INTO fornecedor (cnpj, nome, telefone, email, senha) VALUES (%s, %s, %s, %s, %s)',
            (cnpj, nome, telefone, email, hashed_senha))

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for('home'))
    return render_template('adm.html')

@app.route('/cadastroProduto', methods=['POST', 'GET'])
@login_required
def cadastroProduto():
    if current_user.user_type != 'fornecedor':
        return "Acesso negado.", 403

    connection = conexaodb()
    cursor = connection.cursor()

    if request.method == 'GET':
        cursor.execute("SELECT nome FROM categoria")
        categorias = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        connection.close()
        return render_template('cadastrarP.html', categorias=categorias)

    elif request.method == 'POST':
        cnpj = current_user.id
        categoria = request.form.get('categoria')
        nome = request.form.get('nome')
        codproduto = request.form.get('codproduto')
        descricao = request.form.get('descricao')
        lote = request.form.get('lote')
        vencimento = request.form.get('vencimento')
        quantidade = request.form.get('quantidade')
        valor = request.form.get('valor')
        img = request.files['img']

        extensao = img.filename.rsplit('.', 1)[1]
        url = f'static/img/{codproduto}.{extensao}'
        img.save(url)

        try:
            cursor.execute('''
                INSERT INTO produto 
                (codproduto, lote, vencimento, quantidade, valor, nomeCategoria, descricao, nome, cnpjFornecedor) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (codproduto, lote, vencimento, quantidade, valor, categoria, descricao, nome, cnpj))
            connection.commit()

            cursor.execute('INSERT INTO imagem (codProduto, urlImagem) VALUES (%s, %s)', (codproduto, url))
            connection.commit()
            
            return redirect(url_for('home'))

        except Exception as e:
            connection.rollback()
            print("Erro ao inserir no banco:", e)
            return "Erro ao cadastrar o produto!", 400

        finally:
            cursor.close()
            connection.close()

@app.route('/pesquisar', methods=['GET'])
def pesquisar():
    termo = request.args.get('q', '').strip()
    if not termo:
        return redirect(url_for('home'))

    connection = conexaodb()
    if connection is None:
        return "Erro ao conectar ao banco de dados."

    cursor = connection.cursor()
    cursor.execute("""
    SELECT produto.nome, imagem.urlImagem, produto.codproduto, produto.valor, produto.descricao
    FROM produto
    JOIN imagem ON produto.codproduto = imagem.codProduto
    WHERE LOWER(produto.nome) LIKE %s""", (f"%{termo.lower()}%",))
    resultados = cursor.fetchall()

    cursor.close()
    connection.close()

    tipo_usuario = current_user.user_type if current_user.is_authenticated else None  

    return render_template('home.html', 
                           produtos=resultados, 
                           tipo_usuario=tipo_usuario, 
                           termo_pesquisa=termo,
                           mais_vendidos=[])  


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
