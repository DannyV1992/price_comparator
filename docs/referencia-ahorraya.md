# Referencia: AhorraYa (ahorraya.app)

Notas de lo que se revisó del sitio el 2026-10-04, como guía para la web propia de este proyecto.
Es una referencia de funciones e ideas, no un plan cerrado: la web propia puede agregar lo que haga falta.

Límite de lo revisado: `/app`, `/trends`, `/canasta`, `/comunidad` y el chat se arman con JavaScript en el
navegador, así que solo se vio su estructura y el texto de carga, no los datos. La landing, la página de producto,
`/precios` y `/metodologia` sí vienen completas. Las respuestas de `/faq` están plegadas y no se leyeron.

## Qué es
- Comparador de precios de Costa Rica (web + apps iOS y Android). Lo opera Next Path Solutions (San José).
- Dice cubrir 100+ tiendas y 82.000–90.000 productos: súper, farmacia, perfumería, electrónica, mascotas, carros usados, etc.
- Gratis para el usuario, sin anuncios ni registro. Ingresos: enlaces de redirección/afiliado a las tiendas,
  catálogos que envían los comercios (CSV, Excel o API, sin comisión por venta) y un producto B2B llamado PriceLens
  («inteligencia de precios para empresas»).

## Mapa del sitio
| Ruta | Para qué |
|---|---|
| `/` | Landing: propuesta de valor, categorías destacadas, apps, prensa, preguntas frecuentes |
| `/precios` | Índice público por categoría (9 grupos, 204 categorías) y los productos con mayor diferencia de precio |
| `/precios/categoria/{slug}` | Página de categoría (indexable por buscadores) |
| `/precios/{marca}/{producto}` | Página de producto pública |
| `/app` | La aplicación (buscador y navegación) |
| `/app/producto/{marca}/{producto}` | Producto dentro de la app |
| `/app?view=chat` | Chat con el asistente «Lena» |
| `/trends` | «Bajaron»: productos que cambiaron de precio «esta semana» |
| `/canasta` | «Canasta básica» armada automáticamente «en los 6 súperes» |
| `/comunidad`, `/comunidad/publicar` | Ofertas que sube la gente |
| `/metodologia` | «Cómo comparamos» |
| `/comercios`, `/comercios/registro` | Alianzas y envío de catálogos |
| `/faq`, `/blog`, `/about`, `/contacto`, `/privacidad`, `/terminos`, `/eliminar-cuenta` | Páginas de apoyo |

Las páginas públicas (`/precios/...`) tienen el contenido en el HTML para que Google las indexe; la app no.
Los slugs de categoría mezclan guiones y guiones bajos (`cuidado-personal`, `alimento_perro`).

## Pantallas y funciones
**Menú principal:** Productos, Comunidad, Bajaron, Canasta, Chat.

**Página de producto**
- Foto (o «Sin foto todavía»), marca, nombre.
- «Mejor precio actual» con la tienda, y botón «Ver en {tienda}» que pasa por un enlace de redirección propio.
- Línea de ahorro contra la tienda más cara (en colones y en %).
- Pestañas ancla: «Dónde comprarlo» e «Historial y avisos».
- Tabla «Precios actuales por tienda»: tienda (con logo y sucursal), precio, stock, ahorro contra la más cara, botón «Ver».
  La más barata lleva una insignia «Mejor».
- «Cómo se ha movido el precio»: últimos 90 días; tabla desplegable día por día con precio mínimo, en qué tienda fue
  el más barato y precio máximo.
- Enlace «Volver al comparador». No tiene ordenamiento, productos relacionados ni botón de agregar a lista visibles.

**Catálogo (`/precios`)**
- Grupos: Súper, Electrónica y electrodomésticos, Perfumería, Farmacia, Cuidado de la piel, Suplementos, Salud, Carros, Mascotas.
- Dos niveles: categoría padre (con conteo) y subcategoría. Muchas categorías son planas.
- Sección de «mayor diferencia de precio» con tarjetas (marca, nombre, precio más barato, % de ahorro, precio más alto).

**Comunidad:** pestañas «Lo que suena / Nuevo / Top», botón «Compartir», y secciones Reputación, Ranking y Embajadores.
**Alertas de bajada de precio:** anunciadas, con la etiqueta «próximamente» en la landing.
**Compartir:** enlace a WhatsApp con un mensaje prearmado.

## Metodología (lo más útil)
- **Fuente:** lo que cada tienda publica en su sitio en línea. Algunas tiendas mandan su catálogo directamente.
- **Frecuencia:** cada noche se revisa el catálogo completo. Cada producto muestra cuándo se registró el precio.
- **Precio desactualizado:** si una tienda deja de publicar varios días, el precio se marca como desactualizado y no se muestra como vigente.
- **Cruce de productos:**
  - Con código de barras o número de modelo: es el criterio decisivo, «sin margen de duda».
  - Sin esos códigos: coinciden marca, línea, tamaño y presentación; si falla alguno, no se unen.
  - En caso de duda se dejan separados, porque unir productos distintos inventa ahorros que no existen.
- **Tamaños:** nunca se compara 400 ml con 750 ml. Se muestra precio por unidad (litro, kilo, tableta) cuando tiene sentido;
  el precio de una caja se separa del de una unidad.
- **Diferencia de precio:** entre el precio más alto y el más bajo de las tiendas que lo tienen ese día. No se mide contra
  precios de lista o tachados. Un producto de una sola tienda no muestra diferencia.
- **Errores:** botón en cada producto para reportar una comparación incorrecta; cola de revisión, primero los más reportados;
  la corrección vale para todos.
- **Lo que no explican:** cómo detectan precios atípicos ni cómo tratan los agotados.
- **Aviso:** el precio es el último registrado, puede variar por sucursal o excluir envío; confirmar en la tienda.

## Errores vistos en su página (para no repetirlos)
- En el producto «Saba Protectores Femeninos Diarios Multiforma 15 Und», Compre Bien pasó de ₡637 a ₡2.367 de un día a otro
  mientras Megasuper cuesta ₡640. Parece un dato erróneo, pero lo muestran como real y con un «73% de ahorro».
- La nota al pie dice que la tienda más cara cobra «73% más», pero ₡2.367 contra ₡640 es 270% más. El 73% es el ahorro, no el sobreprecio.

## Dónde está este proyecto frente a AhorraYa
Ya resuelto en dbt (`dbt/models/marts/`):
- Cruce por código de barras **y por nombre**, con productos canónicos (`dim_canonical_products`, `dim_products`) y
  cola de revisión de cruces dudosos con correcciones manuales (`fct_match_review`, seed `match_overrides`).
- Comparación de precios entre tiendas (`fct_price_comparison`) con bandera de precio atípico (`is_price_outlier`).
- Historial diario (`fct_daily_prices`) y eventos de cambio de precio (`fct_price_changes`): base de «Bajaron» y de las gráficas.
- Precio vigente (`fct_current_prices`), canasta (`fct_basket_prices`), índice de precios por tienda (`fct_store_price_index`).
- Cobertura de las descargas (`fct_scrape_coverage`), para saber cuándo un dato no es confiable.

Falta o está por verificar:
- Precio por unidad (hay `unit` y `unit_multiplier` en `store_products`; revisar qué tan completos están).
- Marcar precios desactualizados (hay `last_seen`).
- Reporte de comparación incorrecta (una tabla donde guardar los reportes).
- Cobertura: 8 supermercados frente a 100+ tiendas; sin farmacia, electrónica ni mascotas.
- PriceSmart y los productos de balanza de Perimercados no tienen código de barras comparable.

## Alcance propuesto para la primera versión
1. Buscador por nombre, con foto, marca, precio más bajo y en qué tienda.
2. Página de producto: precios por tienda, ahorro, historial (gráfica + detalle por día), aviso de precio desactualizado.
3. «Bajaron»: cambios de precio recientes.
4. Canasta básica fija con el total por tienda.
5. Precio por unidad.
6. Botón de reportar comparación incorrecta.
7. Páginas generadas en el servidor para que Google las indexe.

Fuera de la primera versión: chat con IA, alertas, comunidad, cuentas de usuario, apps móviles, enlaces de afiliado.

## Decisiones de arquitectura ya hablando
- Misma repo, carpeta `web/`. Despliegue con directorio raíz `web/` y filtros de rutas en los workflows.
- La web no debe leer de Databricks: el warehouse tarda en arrancar, cobra por uso y su token no puede llegar al navegador.
  Un paso final del flujo diario copia los marts de `analytics` a una base ligera (Turso en una base aparte, o Postgres si la
  búsqueda por texto pide más que FTS5).
- Páginas con render en el servidor (Next.js o Astro), no una aplicación que carga todo en el navegador.
