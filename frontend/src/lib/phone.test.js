import { hasMultiplePhones, phoneHref, splitPhoneNumbers } from "./phone";

describe("phone helpers", () => {
  test("keeps one number unchanged", () => {
    expect(splitPhoneNumbers("06 12 34 56 78")).toEqual(["06 12 34 56 78"]);
    expect(phoneHref("06 12 34 56 78")).toBe("tel:0612345678");
  });

  test("splits two numbers separated by a slash", () => {
    expect(splitPhoneNumbers("0327376451 / 0612569563")).toEqual(["0327376451", "0612569563"]);
    expect(splitPhoneNumbers("0327376451/0612569563")).toEqual(["0327376451", "0612569563"]);
  });

  test("ignores empty segments and handles +33", () => {
    expect(splitPhoneNumbers(" / +33 6 12 34 56 78 / ")).toEqual(["+33 6 12 34 56 78"]);
    expect(phoneHref("+33 6 12 34 56 78")).toBe("tel:+33612345678");
  });

  test("returns no link without digits", () => {
    expect(splitPhoneNumbers("")).toEqual([]);
    expect(phoneHref("—")).toBe("");
    expect(hasMultiplePhones("01/02")).toBe(true);
    expect(hasMultiplePhones("01")).toBe(false);
  });
});
