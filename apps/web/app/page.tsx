import { ArrowUpRight, Headphones, ShieldCheck } from "lucide-react";
import Link from "next/link";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.page}>
      <nav className={`shell ${styles.nav}`}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>A</span>
          <span>AssureLine</span>
        </div>
        <span className={styles.pill}>Document-grounded AI</span>
      </nav>

      <section className={`shell ${styles.hero}`}>
        <div className={styles.copy}>
          <p className="eyebrow">Insurance sales, grounded in the policy PDF</p>
          <h1>One product.<br />Two purposeful views.</h1>
          <p className={styles.intro}>
            Customers hear a short policy introduction, ask questions from the
            uploaded document, and choose whether they want a callback. Sales
            teams get the exact context needed to follow up.
          </p>
        </div>
        <div className={styles.signal} aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <div className={styles.signalCore}>LIVE</div>
        </div>
      </section>

      <section className={`shell ${styles.routes}`}>
        <Link className={`${styles.route} ${styles.customer}`} href="/customer">
          <div className={styles.routeIcon}><Headphones size={25} /></div>
          <div>
            <p className="eyebrow">Customer experience</p>
            <h2>Talk to the policy advisor</h2>
            <p>Hear the product pitch, ask policy questions, and request a callback.</p>
          </div>
          <ArrowUpRight className={styles.arrow} />
        </Link>

        <Link className={`${styles.route} ${styles.sales}`} href="/sales">
          <div className={styles.routeIcon}><ShieldCheck size={25} /></div>
          <div>
            <p className="eyebrow">Insurer workspace</p>
            <h2>Review policy leads</h2>
            <p>Upload the PDF, see customer interest, and track callback status.</p>
          </div>
          <ArrowUpRight className={styles.arrow} />
        </Link>
      </section>

      <footer className={`shell ${styles.footer}`}>
        <span>AI voice is disclosed in every customer session.</span>
        <span>Answers are limited to uploaded product documents.</span>
      </footer>
    </main>
  );
}
