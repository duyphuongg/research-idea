/**
 * Best-guess full-size version of a marketplace thumbnail URL.
 * Amazon: drop the size modifiers (`51Ueaw.._AC_UL600_SR600,400_.jpg` → `51Ueaw...jpg`).
 * Etsy: swap the size token for `il_794xN` (sharp, ~5x lighter than il_fullxfull).
 * Anything else is returned unchanged.
 */
export function fullSizeImage(src: string): string {
  if (/amazon\.com\/images\/I\//.test(src)) {
    return src.replace(/\._[^/]*_(\.\w+)$/, "$1");
  }
  if (src.includes("etsystatic.com")) {
    return src.replace(/\/il_\d+x\w+\./, "/il_794xN.");
  }
  return src;
}
