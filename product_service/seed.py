"""
Seed script to populate categories and subcategories.
Run inside the product_service container:
  python seed.py
"""
import asyncio
from database import engine, Base, AsyncSessionLocal
from models import Category, Subcategory, Product
from sqlalchemy.future import select

CATEGORIES_SEED = [
    {
        "name": "Frutas y Verduras",
        "slug": "frutas-verduras",
        "emoji": "🥬",
        "subtitle": "Frescas del día",
        "subcategories": [
            {"name": "Frutas", "slug": "frutas"},
            {"name": "Verduras", "slug": "verduras"},
            {"name": "Hierbas", "slug": "hierbas"},
        ]
    },
    {
        "name": "Lácteos y Huevos",
        "slug": "lacteos-huevos",
        "emoji": "🧀",
        "subtitle": "Leche, quesos y más",
        "subcategories": [
            {"name": "Leches", "slug": "leches"},
            {"name": "Quesos", "slug": "quesos"},
            {"name": "Yogures", "slug": "yogures"},
            {"name": "Huevos", "slug": "huevos"},
        ]
    },
    {
        "name": "Despensa",
        "slug": "despensa",
        "emoji": "🥫",
        "subtitle": "Esenciales de cocina",
        "subcategories": [
            {"name": "Arroz y Pastas", "slug": "arroz-pastas"},
            {"name": "Aceites y Condimentos", "slug": "aceites-condimentos"},
            {"name": "Conservas", "slug": "conservas"},
            {"name": "Harinas", "slug": "harinas"},
        ]
    },
    {
        "name": "Carnes y Pescados",
        "slug": "carnes-pescados",
        "emoji": "🥩",
        "subtitle": "Selección premium",
        "subcategories": [
            {"name": "Carne Vacuna", "slug": "carne-vacuna"},
            {"name": "Pollo", "slug": "pollo"},
            {"name": "Cerdo", "slug": "cerdo"},
            {"name": "Pescados y Mariscos", "slug": "pescados-mariscos"},
        ]
    },
    {
        "name": "Panadería",
        "slug": "panaderia",
        "emoji": "🥖",
        "subtitle": "Horneados artesanales",
        "subcategories": [
            {"name": "Pan", "slug": "pan"},
            {"name": "Facturas y Medialunas", "slug": "facturas-medialunas"},
            {"name": "Tortas y Budines", "slug": "tortas-budines"},
        ]
    },
    {
        "name": "Salud y Belleza",
        "slug": "salud-belleza",
        "emoji": "💊",
        "subtitle": "Cuidado personal",
        "subcategories": [
            {"name": "Higiene Personal", "slug": "higiene-personal"},
            {"name": "Farmacia", "slug": "farmacia"},
            {"name": "Cosmética", "slug": "cosmetica"},
        ]
    },
    {
        "name": "Bebidas",
        "slug": "bebidas",
        "emoji": "🥤",
        "subtitle": "Refrescos y más",
        "subcategories": [
            {"name": "Aguas y Sodas", "slug": "aguas-sodas"},
            {"name": "Gaseosas", "slug": "gaseosas"},
            {"name": "Jugos", "slug": "jugos"},
            {"name": "Cervezas y Vinos", "slug": "cervezas-vinos"},
        ]
    },
    {
        "name": "Congelados",
        "slug": "congelados",
        "emoji": "🧊",
        "subtitle": "Listos para calentar",
        "subcategories": [
            {"name": "Empanadas y Tartas", "slug": "empanadas-tartas"},
            {"name": "Helados", "slug": "helados"},
            {"name": "Vegetales Congelados", "slug": "vegetales-congelados"},
        ]
    },
    {
        "name": "Snacks",
        "slug": "snacks",
        "emoji": "🍿",
        "subtitle": "Para picar",
        "subcategories": [
            {"name": "Papas y Chizitos", "slug": "papas-chizitos"},
            {"name": "Galletitas", "slug": "galletitas"},
            {"name": "Chocolates y Golosinas", "slug": "chocolates-golosinas"},
            {"name": "Frutos Secos", "slug": "frutos-secos"},
        ]
    },
    {
        "name": "Bebé",
        "slug": "bebe",
        "emoji": "🍼",
        "subtitle": "Para los más chiquitos",
        "subcategories": [
            {"name": "Pañales", "slug": "panales"},
            {"name": "Alimentación Bebé", "slug": "alimentacion-bebe"},
            {"name": "Higiene Bebé", "slug": "higiene-bebe"},
        ]
    },
    {
        "name": "Mascotas",
        "slug": "mascotas",
        "emoji": "🐾",
        "subtitle": "Amor animal",
        "subcategories": [
            {"name": "Alimento Perros", "slug": "alimento-perros"},
            {"name": "Alimento Gatos", "slug": "alimento-gatos"},
            {"name": "Accesorios", "slug": "accesorios-mascotas"},
        ]
    },
    {
        "name": "Limpieza",
        "slug": "limpieza",
        "emoji": "🧹",
        "subtitle": "Hogar impecable",
        "subcategories": [
            {"name": "Lavandina y Desinfectantes", "slug": "lavandina-desinfectantes"},
            {"name": "Detergentes", "slug": "detergentes"},
            {"name": "Bolsas y Papeles", "slug": "bolsas-papeles"},
        ]
    },
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = await db.execute(select(Category))
        if existing.scalars().first():
            print("⚠️  Categories already exist. Skipping categories seed.")
        else:
            for cat_data in CATEGORIES_SEED:
                subcats_data = cat_data.pop("subcategories")
                cat = Category(**cat_data)
                db.add(cat)
                await db.flush()  # Get the cat.id

                for sub_data in subcats_data:
                    sub = Subcategory(**sub_data, category_id=cat.id)
                    db.add(sub)

            await db.commit()
            print("✅ Seeded categories and subcategories successfully!")

        # Now migrate existing products: match their 'category' string to a subcategory
        products_result = await db.execute(select(Product).where(Product.subcategory_id == None))
        products = products_result.scalars().all()

        if products:
            subcats_result = await db.execute(select(Subcategory))
            all_subcats = subcats_result.scalars().all()

            # Build a map: category_slug -> first subcategory id
            cats_result = await db.execute(select(Category))
            all_cats = cats_result.scalars().all()
            slug_to_first_sub = {}
            for cat in all_cats:
                subs = [s for s in all_subcats if s.category_id == cat.id]
                if subs:
                    slug_to_first_sub[cat.slug] = subs[0].id

            for product in products:
                if product.category and product.category in slug_to_first_sub:
                    product.subcategory_id = slug_to_first_sub[product.category]

            await db.commit()
        print(f"✅ Migrated {len(products)} existing products to subcategories.")
        
        # Seed Products
        PRODUCTS_SEED = [
            {"name": "Manzana Roja", "price": 1200, "image_url": "🍎", "description": "Manzana roja deliciosa y crujiente", "subcategory_slug": "frutas"},
            {"name": "Banana Cavendish", "price": 1500, "image_url": "🍌", "description": "Bananas de Ecuador, paquete 1kg", "subcategory_slug": "frutas"},
            {"name": "Lechuga Mantecosa", "price": 800, "image_url": "🥬", "description": "Lechuga fresca hidroponica", "subcategory_slug": "verduras"},
            {"name": "Leche Entera La Serenísima", "price": 1300, "image_url": "🥛", "description": "Sachet 1 litro", "subcategory_slug": "leches"},
            {"name": "Queso Cremoso", "price": 5500, "image_url": "🧀", "description": "Queso cremoso por horma", "subcategory_slug": "quesos"},
            {"name": "Huevos Blancos x12", "price": 2500, "image_url": "🥚", "description": "Docena de huevos tamaño grande", "subcategory_slug": "huevos"},
            {"name": "Fideos Tirabuzón", "price": 950, "image_url": "🍝", "description": "Fideos secos Lucchetti 500g", "subcategory_slug": "arroz-pastas"},
            {"name": "Aceite de Girasol", "price": 1800, "image_url": "🛢️", "description": "Aceite Cocinero 900ml", "subcategory_slug": "aceites-condimentos"},
            {"name": "Bife de Chorizo", "price": 8500, "image_url": "🥩", "description": "Corte premium envasado al vacío 1kg", "subcategory_slug": "carne-vacuna"},
            {"name": "Pechuga de Pollo", "price": 4200, "image_url": "🍗", "description": "Pechuga sin hueso ni piel 1kg", "subcategory_slug": "pollo"},
            {"name": "Pan Francés", "price": 1200, "image_url": "🥖", "description": "Pan francés horneado en el día 1kg", "subcategory_slug": "pan"},
            {"name": "Medialunas de Manteca", "price": 3500, "image_url": "🥐", "description": "Docena de medialunas de manteca", "subcategory_slug": "facturas-medialunas"},
            {"name": "Jabón de Tocador", "price": 600, "image_url": "🧼", "description": "Jabón Dove original 90g", "subcategory_slug": "higiene-personal"},
            {"name": "Agua Mineral Sin Gas", "price": 750, "image_url": "💧", "description": "Botella 1.5L Villavicencio", "subcategory_slug": "aguas-sodas"},
            {"name": "Coca-Cola Original", "price": 2200, "image_url": "🥤", "description": "Botella 2.25L", "subcategory_slug": "gaseosas"},
            {"name": "Cerveza Quilmes", "price": 1900, "image_url": "🍺", "description": "Lata 473ml", "subcategory_slug": "cervezas-vinos"},
            {"name": "Papas Fritas Lays", "price": 1800, "image_url": "🍟", "description": "Paquete clásico 145g", "subcategory_slug": "papas-chizitos"},
            {"name": "Chocolate Milka", "price": 1500, "image_url": "🍫", "description": "Chocolate con leche 150g", "subcategory_slug": "chocolates-golosinas"},
            {"name": "Alimento Pedigree", "price": 15000, "image_url": "🦮", "description": "Alimento para perro adulto 15kg", "subcategory_slug": "alimento-perros"},
            {"name": "Detergente Ala", "price": 1200, "image_url": "🫧", "description": "Detergente limón 500ml", "subcategory_slug": "detergentes"},
        ]
        
        # Check if we already have these seeded products
        existing_products_result = await db.execute(select(Product))
        if len(existing_products_result.scalars().all()) < 10:
            print("Seeding some additional products...")
            subcats_result = await db.execute(select(Subcategory))
            all_subcats = subcats_result.scalars().all()
            slug_to_subcat_id = {s.slug: s.id for s in all_subcats}
            
            for prod_data in PRODUCTS_SEED:
                sub_slug = prod_data.pop("subcategory_slug")
                if sub_slug in slug_to_subcat_id:
                    prod_data["subcategory_id"] = slug_to_subcat_id[sub_slug]
                    new_prod = Product(**prod_data)
                    db.add(new_prod)
            
            await db.commit()
            print("✅ Seeded products successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
