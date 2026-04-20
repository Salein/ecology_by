export function formatWasteTypeDisplay(wasteTypeName: string | null | undefined): string {
  let value = (wasteTypeName || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  if (!value) return "—";

  const cutMarkers = [
    /\b(?:Объект|Собственник)\b/i,
    /(^|[^A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)(?=$|[^A-Za-zА-Яа-яЁё])/i,
    /\b\d{6}\b/,
    /(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|(?:^|[^A-Za-zА-Яа-яЁё])тел\.?(?=$|[^A-Za-zА-Яа-яЁё])|(?:^|[^A-Za-zА-Яа-яЁё])факс(?=$|[^A-Za-zА-Яа-яЁё]))/i,
    /\(/,
    /\bв\s+соответствии\s+с\s+законодательством\b/i,
    /\bоб\s+охране\s+окружающей\s+среды\b/i,
    /(?:дробильно-сортировочн(?:ый|ая|ое|ые)|дробильн(?:ый|ая|ое|ые)|стационарн(?:ый|ая|ое|ые)|мобильн(?:ый|ая|ое|ые)|комплекс|установка|цех|участок|площадк[аи]|полигон|пила|экскаватор|гидромолот)/i,
  ];
  const cuts = cutMarkers.map((re) => value.search(re)).filter((idx) => idx >= 0);
  if (cuts.length > 0) value = value.slice(0, Math.min(...cuts));

  value = value.replace(/^[*•"'«»\s\-–—]+/, "").replace(/[;,.:\-–—\s]+$/g, "").trim();
  return value || "—";
}
