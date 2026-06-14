"use client";

import { FormEvent, useState } from "react";
import { isValidDemoPassword } from "./auth";
import styles from "./sales-dashboard.module.css";

export function DemoAuth({
  password,
  onAuthenticated,
}: {
  password: string;
  onAuthenticated: () => void;
}) {
  const [value, setValue] = useState("");
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (isValidDemoPassword(value, password)) {
      window.sessionStorage.setItem("advisor-console-auth", "true");
      onAuthenticated();
      return;
    }
    setInvalid(true);
  }

  return (
    <main className={styles.authPage}>
      <section className={styles.authBrand}>
        <div className={styles.authBrandInner}>
          <div className={styles.logoLockup}>
            <span className={styles.logoMark}>AP</span>
            <span>AssureLine</span>
          </div>
          <p className={styles.authKicker}>Advisor operations</p>
          <h1>Every conversation, ready for a human follow-through.</h1>
          <p className={styles.authCopy}>
            Review grounded customer conversations, prioritize callback intent,
            and close the loop with a clear record of every action.
          </p>
          <div className={styles.authMetric}>
            <strong>01</strong>
            <span>One desk for live AI-qualified leads</span>
          </div>
        </div>
      </section>
      <section className={styles.authFormArea}>
        <form className={styles.authForm} onSubmit={submit}>
          <p className={styles.eyebrow}>Restricted workspace</p>
          <h2>Sales team sign in</h2>
          <p>Enter the demo access code to open the advisor console.</p>
          <label htmlFor="sales-password">Access code</label>
          <input
            id="sales-password"
            autoComplete="current-password"
            autoFocus
            onChange={(event) => {
              setValue(event.target.value);
              setInvalid(false);
            }}
            placeholder="Enter access code"
            type="password"
            value={value}
          />
          {invalid ? (
            <p className={styles.formError} role="alert">
              That access code is not valid. Try <code>demo-sales</code>.
            </p>
          ) : null}
          <button className={styles.authSubmit} type="submit">
            Open advisor console
          </button>
          <p className={styles.authHint}>
            Demo default: <code>demo-sales</code>
          </p>
        </form>
      </section>
    </main>
  );
}
