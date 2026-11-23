import {
  auth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  signOut,
  onAuthStateChanged
} from "./firebase-config.js";

const $ = (selector) => document.querySelector(selector);
const profileKey = (uid) => `roadguard_profile_${uid}`;
const nameKey = (uid) => `roadguard_name_${uid}`;

function showForm(name) {
  document.querySelectorAll(".auth-form").forEach((form) => {
    form.classList.toggle("active", form.id === `${name}-form`);
  });
  document.querySelectorAll(".auth-error").forEach((error) => {
    error.textContent = "";
  });
}

function showError(elementId, message) {
  const element = $(elementId);
  if (element) element.textContent = message;
}

function isAcceptedEmail(email) {
  return /^[A-Za-z][A-Za-z0-9._%+-]{1,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(email);
}

function isStrongPassword(password) {
  return /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]).{8,}$/.test(password);
}

async function syncBackendUser(user, name) {
  const idToken = await user.getIdToken(true);
  const response = await fetch("/api/auth/firebase-sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${idToken}`
    },
    credentials: "same-origin",
    body: JSON.stringify({ name: name || user.displayName || user.email.split("@")[0] })
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Could not connect your account to RoadGuard backend.");
  sessionStorage.setItem("roadguard_csrf", body.csrfToken);
  return body;
}

async function enterApp(user) {
  const savedName = localStorage.getItem(nameKey(user.uid));
  const name = savedName || user.displayName || user.email.split("@")[0];

  document.querySelector("#auth-screen").classList.add("hidden");
  $("#avatar").textContent = name.charAt(0).toUpperCase();
  $("#page-title").textContent = `Good morning, ${name}.`;

  const savedProfile = localStorage.getItem(profileKey(user.uid));
  if (!savedProfile) {
    $("#onboard-name").value = name;
    $("#onboarding").classList.remove("hidden");
  } else {
    $("#onboarding").classList.add("hidden");
  }

  if (typeof hydrate === "function") await hydrate();
}

$("#show-register").onclick = () => showForm("register");
$("#show-login").onclick = () => showForm("login");

$("#register-submit").onclick = async () => {
  const name = $("#register-name").value.trim();
  const email = $("#register-email").value.trim();
  const password = $("#register-password").value;
  const confirmPassword = $("#confirm-password").value;
  showError("#register-error", "");

  if (!name || !email || !password || !confirmPassword) {
    showError("#register-error", "Enter your name, email, password, and confirm password.");
    return;
  }
  if (!isAcceptedEmail(email)) {
    showError("#register-error", "Enter a valid email such as you@gmail.com.");
    return;
  }
  if (!isStrongPassword(password)) {
    showError("#register-error", "Password needs 8+ characters with uppercase, lowercase, number, and special character.");
    return;
  }
  if (password !== confirmPassword) {
    showError("#register-error", "Passwords do not match.");
    return;
  }

  try {
    const credential = await createUserWithEmailAndPassword(auth, email, password);
    localStorage.setItem(nameKey(credential.user.uid), name);
    await sendEmailVerification(credential.user);
    await signOut(auth);
    showForm("login");
    showError("#login-error", "Verification email sent. Check Inbox or Spam, click the verification link, then sign in.");
  } catch (error) {
    showError("#register-error", error.message);
  }
};

$("#login-submit").onclick = async () => {
  const email = $("#login-email").value.trim();
  const password = $("#login-password").value;
  showError("#login-error", "");

  try {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    await credential.user.reload();

    if (!credential.user.emailVerified) {
      await signOut(auth);
      showError("#login-error", "Verify your email first. Check Inbox and Spam folder.");
      return;
    }

    await syncBackendUser(credential.user);
    await enterApp(credential.user);
  } catch (error) {
    showError("#login-error", "Login failed: " + error.message);
  }
};

$("#onboard-submit").onclick = async () => {
  const user = auth.currentUser;
  const profile = {
    age: $("#onboard-age").value,
    experienceYears: $("#onboard-exp").value,
    vehicleType: $("#onboard-vehicle").value,
    emergencyNotes: $("#onboard-notes").value
  };

  if (!profile.age || !profile.experienceYears || !profile.vehicleType) {
    showError("#onboard-error", "Enter your age, driving experience, and vehicle type.");
    return;
  }

  localStorage.setItem(profileKey(user.uid), JSON.stringify(profile));
  try {
    const response = await fetch("/api/driver-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": sessionStorage.getItem("roadguard_csrf") || "" },
      body: JSON.stringify(profile)
    });
    if (!response.ok) throw new Error("Could not save driver profile.");
  } catch (error) {
    showError("#onboard-error", error.message);
    return;
  }
  $("#onboarding").classList.add("hidden");
};

$("#logout").onclick = async () => {
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": sessionStorage.getItem("roadguard_csrf") || "" },
      credentials: "same-origin"
    });
  } catch (_) {}
  sessionStorage.removeItem("roadguard_csrf");
  await signOut(auth);
  $("#auth-screen").classList.remove("hidden");
  $("#onboarding").classList.add("hidden");
  showForm("login");
};

onAuthStateChanged(auth, async (user) => {
  if (!user) return;
  try {
    await user.reload();
    if (user.emailVerified) {
      await syncBackendUser(user);
      await enterApp(user);
    } else {
      await signOut(auth);
      $("#auth-screen").classList.remove("hidden");
      showForm("login");
    }
  } catch (error) {
    console.error("RoadGuard authentication sync failed:", error);
  }
});
