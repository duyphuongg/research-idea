/**
 * Best-guess full-size version of a marketplace thumbnail URL.
 * Etsy: swap the size token for `il_794xN` (sharp, ~5x lighter than il_fullxfull).
 * Anything else is returned unchanged.
 */
export function fullSizeImage(src: string): string {
  if (src.includes("etsystatic.com")) {
    return src.replace(/\/il_\d+x\w+\./, "/il_794xN.");
  }
  return src;
}
