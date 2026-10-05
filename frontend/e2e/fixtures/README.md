# Фотографии кодов для теста сканера

- `ean13.png` — штрихкод EAN-13 `4601669002013`.
- `datamatrix.png` — DataMatrix как на упаковке с «Честным знаком»: GTIN `04601669002013`, серийный номер `ABCDEFGHIJKL`,
  срок годности 31.05.2027, партия `AB1234`.

Сделаны один раз пакетом `bwip-js` (в проект он не добавлен, он нужен только для генерации):

```js
const bwipjs = require('bwip-js')
await bwipjs.toBuffer({ bcid: 'ean13', text: '4601669002013', scale: 4, height: 18, includetext: true, backgroundcolor: 'FFFFFF', paddingwidth: 20, paddingheight: 20 })
await bwipjs.toBuffer({ bcid: 'gs1datamatrix', scale: 8, backgroundcolor: 'FFFFFF', paddingwidth: 20, paddingheight: 20,
  text: '(01)04601669002013(21)ABCDEFGHIJKL(17)270531(10)AB1234' })
```
