// Spec #611 J2 (ticket #614; mockup-613-filling.html 一 A): on 註冊, 用 LINE 取名稱 and 忘記密碼,
// an email whose part after the @ is one or two letters off a common one is asked about under
// the field, with a button that puts it right. Only asked, never stopped; compared here in the
// browser, nothing sent anywhere. The server sends the place empty (#id_email_hint), so without
// JavaScript nothing shows.
(function () {
  const input = document.getElementById("id_email");
  const hint = document.getElementById("id_email_hint");

  // The seven asked about, in this order when two are as close.
  const COMMON = [
    "gmail.com",
    "yahoo.com.tw",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "msa.hinet.net",
  ];
  // Real ones that look like one of the seven: Yahoo's other address, the free mail.com and
  // email.com, Yahoo in nine other places (listed, so yahoo.com.wt is still asked about), HiNet's
  // other mail hosts ms1 to ms99.
  const REAL = [
    /^ymail\.com$/,
    /^e?mail\.com$/,
    /^yahoo\.com\.(hk|sg|au|my|ph|vn|br|mx|ar)$/,
    /^ms[1-9][0-9]?\.hinet\.net$/,
  ];

  // Letters added, taken out or changed, two side by side swapped counting as one.
  function lettersOff(a, b) {
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        const changed = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + changed);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        }
      }
    }
    return d[a.length][b.length];
  }

  // The email as meant, or null: what is before the last @ as typed, the closest of the seven
  // one or two letters off after it.
  function meant(email) {
    const at = email.lastIndexOf("@");
    if (at < 0) return null;
    const domain = email.slice(at + 1).toLowerCase();
    if (COMMON.includes(domain) || REAL.some((real) => real.test(domain))) return null;
    let best = null;
    let bestOff = 3;
    for (const common of COMMON) {
      const off = lettersOff(domain, common);
      if (off < bestOff) [best, bestOff] = [common, off];
    }
    return best && `${email.slice(0, at)}@${best}`;
  }

  let asked = null;

  function check() {
    const suggestion = meant(input.value.trim());
    // The same question left as it is, so screen readers do not hear it again.
    if (suggestion && suggestion === asked) return;
    asked = suggestion;
    if (!suggestion) {
      hint.replaceChildren();
      return;
    }
    const question = document.createElement("span");
    const email = document.createElement("b");
    email.textContent = suggestion;
    question.append("您是不是要打 ", email, "？");
    const fix = document.createElement("button");
    fix.type = "button";
    fix.className = "btn btn-outline-primary email-hint-fix";
    fix.textContent = "按這裡改";
    fix.addEventListener("click", () => {
      input.value = suggestion;
      input.focus();
      asked = null;
      const done = document.createElement("span");
      done.className = "visually-hidden";
      done.textContent = `已改成 ${suggestion}`;
      hint.replaceChildren(done);
    });
    hint.replaceChildren(question, fix);
  }

  // Not while typing: asking before the email is finished would only annoy.
  input.addEventListener("blur", check);
  // An email already there on arrival, such as one the server kept after a mistake elsewhere.
  check();
})();
