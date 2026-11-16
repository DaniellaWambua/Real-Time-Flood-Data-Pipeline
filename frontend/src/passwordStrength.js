// The browser side of backend/password_policy.py: the same rules, run as the person types so they can
// see how strong a password is before saving. The server still makes the final check.
// zxcvbn and its word lists are loaded only when a password field is first used.
export const MIN_LENGTH = 12;
const MIN_SCORE = 3;
const SYSTEM_WORDS = ["flood", "floods", "nairobi", "mathare", "ngong", "river", "warning", "password", "strathmore", "kenya"];

let loading = null;

function loadZxcvbn() {
  if (!loading) {
    loading = Promise.all([
      import("@zxcvbn-ts/core"),
      import("@zxcvbn-ts/language-common"),
      import("@zxcvbn-ts/language-en"),
    ]).then(([core, common, en]) => {
      core.zxcvbnOptions.setOptions({
        translations: en.translations,
        graphs: common.adjacencyGraphs,
        dictionary: { ...common.dictionary, ...en.dictionary },
      });
      return core.zxcvbn;
    });
  }
  return loading;
}

function personalWords({ username, fullName, email, organisation } = {}) {
  const words = [username ?? ""];
  if (email) words.push(email.split("@")[0]);
  [fullName, organisation].forEach((text) => words.push(...(text ?? "").split(/\s+/)));
  return words.map((w) => w.toLowerCase()).filter((w) => w.length >= 3);
}

function without(password, words) {
  let rest = password.toLowerCase();
  [...words].sort((a, b) => b.length - a.length).forEach((w) => {
    rest = rest.split(w).join("");
  });
  return rest;
}

// { score 0-4, ok, message } for the password typed so far
export async function assess(password, person) {
  if (!password) return { score: 0, ok: false, message: "" };
  const zxcvbn = await loadZxcvbn();
  const personal = personalWords(person);
  const lowered = password.toLowerCase();

  const result = zxcvbn(password, [...personal, ...SYSTEM_WORDS]);
  const score = password.length < MIN_LENGTH ? Math.min(result.score, 1) : result.score;

  if (password.length < MIN_LENGTH) {
    return { score, ok: false, message: `At least ${MIN_LENGTH} characters (${password.length} so far)` };
  }
  const own = [person?.username, (person?.email ?? "").split("@")[0]].filter((w) => w && w.length >= 4);
  if (own.some((w) => lowered.includes(w.toLowerCase()))) {
    return { score: 0, ok: false, message: "Leave out your username and email address" };
  }
  if (result.score < MIN_SCORE) {
    const hint = result.feedback.warning || result.feedback.suggestions[0] || "Add another word or two";
    return { score, ok: false, message: hint };
  }
  const rest = without(password, [...personal, ...SYSTEM_WORDS]);
  if (!rest.trim() || zxcvbn(rest).score < MIN_SCORE) {
    return { score: 2, ok: false, message: "Add words of your own, not just your name or words like flood or Mathare" };
  }
  return { score, ok: true, message: score === 4 ? "Very strong" : "Strong" };
}
