# Datos sintéticos de demostración

**Estos datos son ficticios.** Sirven para ejecutar y probar el pipeline sin internet. No
representan a ninguna entidad, proveedor ni proceso real.

| Archivo | Contenido |
| --- | --- |
| `ocds_sample.jsonl` | 1 200 procesos OCDS (releases compilados), un proceso por línea |
| `sanciones_sample.xlsx` | Registro de sanciones con títulos sobre la tabla (para probar la detección de encabezados) |
| `tipo_cambio_sample.csv` | Tipo de cambio diario S/ por US$ simulado |

Características:

* Entidades, proveedores y consorcios se llaman "DEMO" (por ejemplo `HOSPITAL DEMO 03`,
  `PROVEEDOR DEMO 015 S.R.L.`, `CONSORCIO DEMO 07`).
* Los OCID usan el prefijo ficticio `ocds-demo00`; los RUC, el rango `20999xxxxxx` con dígito
  verificador válido.
* Imitan la estructura de la publicación real del OECE (ver
  [docs/04_fuentes_de_datos.md](../../docs/04_fuentes_de_datos.md)):
  * entidades identificadas con `PE-CONSUCODE-<código>` y RUC en `additionalIdentifiers`
    (una entidad no publica RUC);
  * `address.region` con una provincia en algunas entidades y el departamento en
    `address.department`;
  * `tenderPeriod` con inicio = fin en cerca del 40 % de los procesos competitivos y en todas las
    contrataciones directas, y `enquiryPeriod` con su duración;
  * estados vacíos en la mayoría de procesos, adjudicaciones y contratos;
  * valores referenciales en 0 (4 %) y `value.amount_PEN` en el valor referencial;
  * consorcios ganadores con código interno de 7 dígitos (sin RUC) y proveedores sin dirección;
  * procesos sin `tender.tenderers` (los postores están en `parties`).
* Incluyen a propósito los problemas de calidad documentados en la fuente real (postores
  duplicados, contratos sin estado o sin adjudicación vinculada) y un RUC inválido en sanciones.
* Incluyen patrones que activan cada indicador de riesgo (postor único, concentración, sanciones
  vigentes, etc.).

Para regenerarlos (resultado idéntico con la misma semilla):

```bash
contrataciones sample --n 1200 --seed 2026
```
