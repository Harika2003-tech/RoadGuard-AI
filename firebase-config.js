import { initializeApp } from
  "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";

import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signOut,
  onAuthStateChanged
} from
  "https://www.gstatic.com/firebasejs/11.0.2/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyDQETIUQ9JkZqS5DWnH-30bD5V9WT-O_CM",
  authDomain: "roadguard-ai-136c8.firebaseapp.com",
  projectId: "roadguard-ai-136c8",
  storageBucket: "roadguard-ai-136c8.firebasestorage.app",
  messagingSenderId: "675230727243",
  appId: "1:675230727243:web:8657f67aec42605363a1ce",
  measurementId: "G-2KYBVV29G7"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

export {
  auth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signOut,
  onAuthStateChanged
};