from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, TextAreaField, SubmitField, PasswordField, FileField
from wtforms.validators import DataRequired, Length, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import os
import csv
from io import StringIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_change_this_now'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///store_pro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# نموذج المستخدم
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# نماذج البيانات
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    buy_price_usd = db.Column(db.Float)
    buy_price_sar = db.Column(db.Float)
    sell_price = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float)
    quantity = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    image = db.Column(db.String(100))  # مسار الصورة

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    total_price = db.Column(db.Float)
    discount = db.Column(db.Float, default=0)
    final_amount = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('PurchaseItem', backref='purchase', lazy=True, cascade='all, delete-orphan')

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    product = db.relationship('Product', backref='purchase_items')

# نماذج WTForms
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=4, max=20)])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('دخول')

class RegisterForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=4, max=20)])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('تسجيل')

class ProductForm(FlaskForm):
    name = StringField('اسم المنتج', validators=[DataRequired()])
    category = StringField('التصنيف')
    buy_price_usd = FloatField('سعر الشراء (دولار)', validators=[DataRequired(), NumberRange(min=0)])
    sell_price = FloatField('سعر البيع (ريال)', validators=[DataRequired(), NumberRange(min=0)])
    quantity = IntegerField('الكمية', validators=[DataRequired(), NumberRange(min=0)])
    notes = TextAreaField('الملاحظات')
    image = FileField('صورة المنتج')
    submit = SubmitField('حفظ')

class PurchaseForm(FlaskForm):
    customer_name = StringField('اسم المشتري', validators=[DataRequired()])
    discount = FloatField('الخصم', default=0, validators=[NumberRange(min=0)])
    submit = SubmitField('تسجيل الشراء')

# إنشاء الجداول
with app.app_context():
    db.create_all()
    if not User.query.first():
        user = User(username='admin', password_hash=generate_password_hash('admin'))
        db.session.add(user)
        db.session.commit()

USD_TO_SAR = 3.75

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# تسجيل الدخول
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة!')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('اسم المستخدم موجود بالفعل!')
        else:
            user = User(username=form.username.data, password_hash=generate_password_hash(form.password.data))
            db.session.add(user)
            db.session.commit()
            flash('تم التسجيل بنجاح! قم بالدخول.')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# الصفحة الرئيسية (Dashboard) - مصححة
@app.route('/')
@login_required
def dashboard():
    # تصحيح: استخدام filter() بدلاً من filter_by() للمقارنات
    products = Product.query.filter(Product.quantity > 0).all()
    total_products = len(products)
    total_quantity = sum(p.quantity for p in products)
    total_revenue_potential = sum(p.sell_price * p.quantity for p in products)
    total_profits = sum(p.profit * p.quantity for p in products)  # أرباح محتملة
    top_products = Product.query.order_by(Product.sell_price.desc()).limit(5).all()
    low_stock = Product.query.filter(Product.quantity <= 5, Product.quantity > 0).all()
    
    # بيانات للرسوم (مبيعات، أرباح)
    top_names = [p.name for p in top_products]
    top_prices = [p.sell_price for p in top_products]
    profits_data = [p.profit for p in top_products]
    
    # إحصائيات المبيعات
    total_sales = sum(purchase.final_amount for purchase in Purchase.query.all())
    
    return render_template('dashboard.html',
                          total_products=total_products,
                          total_quantity=total_quantity,
                          total_revenue_potential=total_revenue_potential,
                          total_profits=total_profits,
                          total_sales=total_sales,
                          top_products=top_products,
                          low_stock=low_stock,
                          top_names=top_names,
                          top_prices=top_prices,
                          profits_data=profits_data)

# إضافة/تعديل منتج
@app.route('/add_product', methods=['GET', 'POST'])
@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
@login_required
def product_page(id=None):
    form = ProductForm()
    product = Product.query.get_or_404(id) if id else None
    if form.validate_on_submit():
        if product:
            product.name = form.name.data
            product.category = form.category.data
            product.buy_price_usd = form.buy_price_usd.data
            product.buy_price_sar = form.buy_price_usd.data * USD_TO_SAR
            product.sell_price = form.sell_price.data
            product.profit = product.sell_price - product.buy_price_sar
            product.quantity = form.quantity.data
            product.notes = form.notes.data
        else:
            product = Product(
                name=form.name.data,
                category=form.category.data,
                buy_price_usd=form.buy_price_usd.data,
                buy_price_sar=form.buy_price_usd.data * USD_TO_SAR,
                sell_price=form.sell_price.data,
                profit=form.sell_price.data - (form.buy_price_usd.data * USD_TO_SAR),
                quantity=form.quantity.data,
                notes=form.notes.data
            )
            db.session.add(product)
        
        # رفع الصورة
        if 'image' in request.files and allowed_file(request.files['image'].filename):
            filename = secure_filename(form.image.data.filename)
            form.image.data.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            product.image = filename
        
        db.session.commit()
        flash('تم حفظ المنتج بنجاح!')
        return redirect(url_for('stock'))
    
    if product:
        form.name.data = product.name
        form.category.data = product.category
        form.buy_price_usd.data = product.buy_price_usd
        form.sell_price.data = product.sell_price
        form.quantity.data = product.quantity
        form.notes.data = product.notes
    
    return render_template('product_form.html', form=form, product=product, is_edit=bool(product))

# المخزون
@app.route('/stock')
@login_required
def stock():
    products = Product.query.all()
    return render_template('stock.html', products=products)

@app.route('/delete_product/<int:id>')
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('تم حذف المنتج بنجاح!')
    return redirect(url_for('stock'))

# الشراء - مصحح
@app.route('/purchase', methods=['GET', 'POST'])
@login_required
def purchase():
    form = PurchaseForm()
    if form.validate_on_submit():
        # جلب المنتجات من JSON (من JS)
        items_data = json.loads(request.form.get('items', '[]'))
        total_price = sum(item['price'] * item['quantity'] for item in items_data)
        discount = form.discount.data
        final_amount = total_price - discount
        
        purchase = Purchase(
            customer_name=form.customer_name.data,
            total_price=total_price,
            discount=discount,
            final_amount=final_amount
        )
        db.session.add(purchase)
        db.session.flush()  # للحصول على ID
        
        for item in items_data:
            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=item['id'],
                quantity=item['quantity']
            )
            db.session.add(purchase_item)
            # تحديث الكمية
            prod = Product.query.get(item['id'])
            prod.quantity -= item['quantity']
            if prod.quantity <= 0:
                db.session.delete(prod)
        
        db.session.commit()
        flash('تم تسجيل الشراء بنجاح!')
        return redirect(url_for('invoices'))
    
    # تصحيح: استخدام filter() بدلاً من filter_by()
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('purchase.html', form=form, products=products)

# الفواتير
@app.route('/invoices')
@login_required
def invoices():
    purchases = Purchase.query.order_by(Purchase.date.desc()).all()
    return render_template('invoices.html', purchases=purchases)

@app.route('/export_invoices')
@login_required
def export_invoices():
    purchases = Purchase.query.all()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'المشتري', 'الإجمالي', 'الخصم', 'النهائي', 'التاريخ'])
    for p in purchases:
        cw.writerow([p.id, p.customer_name, p.total_price, p.discount, p.final_amount, p.date])
    output = si.getvalue()
    return send_file(StringIO(output), mimetype='text/csv', as_attachment=True, download_name='invoices.csv')

if __name__ == '__main__':
    app.run(debug=True)