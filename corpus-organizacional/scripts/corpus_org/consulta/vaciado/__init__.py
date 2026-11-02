"""Vaciado de un formulario K4 (levantamiento del puesto) en la plantilla metodologica de carga laboral.

Todo con la biblioteca estandar (``zipfile`` y ``xml``): en Copilot no se puede instalar nada y ``openpyxl`` borraria
las listas desplegables de la plantilla. La plantilla se edita en el XML de sus hojas y el resto del paquete queda
byte a byte igual.

- ``xlsx``: lector de libros (valores, formulas, hojas ocultas, celdas combinadas, notas, colores).
- ``k4``: interpreta el K4 y entrega sus datos ya limpios.
- ``valores``: normaliza tiempos, volumenes, frecuencias y listas.
- ``paquete`` y ``hoja_xml``: escritura segura sobre el XML de la plantilla.
- ``plan`` y ``metodologia``: que va en cada celda y la hoja de puntos a validar.
- ``verificacion``: relee el archivo escrito y lo rechaza si algo no coincide.
"""
