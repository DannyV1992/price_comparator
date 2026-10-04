{#-
  Clave de código de barras para cruzar productos entre tiendas.
  Deja solo los dígitos, quita los ceros a la izquierda (unas tiendas los agregan y otras no) y
  rellena a 14 dígitos (GTIN-14), así EAN-13 y UPC-12 del mismo producto dan la misma clave.
  Devuelve NULL si quedan menos de 8 dígitos (códigos de balanza de frutas y verduras, no son
  códigos de barras) o más de 14.
-#}
{% macro normalize_ean(column) -%}
    case
        when length(trim(leading '0' from regexp_replace({{ column }}, '[^0-9]', ''))) between 8 and 14
        then lpad(trim(leading '0' from regexp_replace({{ column }}, '[^0-9]', '')), 14, '0')
    end
{%- endmacro %}
