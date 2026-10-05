import { Comparison } from "@/components/Comparison";
import { ListPanel } from "@/components/ListPanel";
import { Search } from "@/components/Search";

export default function Home() {
  return (
    <main className="layout">
      <header className="top">
        <h1>Comparador de súper</h1>
        <p>Arma tu lista de compras eligiendo cada producto.</p>
      </header>
      {/* El panel de la lista se queda fijo solo dentro de esta zona; la comparación va debajo, a todo el ancho. */}
      <div className="work">
        <Search />
        <ListPanel />
      </div>
      <Comparison />
    </main>
  );
}
