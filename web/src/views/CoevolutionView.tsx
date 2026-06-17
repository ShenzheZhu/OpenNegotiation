import { useState } from "react";
import {
  EuiPanel,
  EuiText,
  EuiSpacer,
  EuiButton,
  EuiCallOut,
  EuiBasicTable,
  EuiFlexGroup,
  EuiFlexItem,
  EuiCode,
} from "@elastic/eui";
import {
  coevolveApi,
  type Coevolution,
  type GenerationRecord,
  type GenomeScore,
} from "../api/client";

const genes = (g: GenomeScore): string =>
  Object.entries(g.genes)
    .map(([k, v]) => `${k}=${v.toFixed(2)}`)
    .join(", ");

export function CoevolutionView() {
  const [result, setResult] = useState<Coevolution | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = () => {
    setBusy(true);
    setError(null);
    coevolveApi
      .run({ generations: 5, population: 6, scenario_count: 2 })
      .then(setResult)
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(false));
  };

  const genColumns = [
    { field: "generation", name: "Gen", width: "60px" },
    {
      name: "Buyer best / mean",
      render: (r: GenerationRecord) =>
        `${r.buyer_best_fitness.toFixed(3)} / ${r.buyer_mean_fitness.toFixed(3)}`,
    },
    {
      name: "Seller best / mean",
      render: (r: GenerationRecord) =>
        `${r.seller_best_fitness.toFixed(3)} / ${r.seller_mean_fitness.toFixed(3)}`,
    },
  ];

  return (
    <EuiPanel>
      <EuiFlexGroup alignItems="center">
        <EuiFlexItem>
          <EuiText>
            <h2>Co-evolution</h2>
            <p>
              Two strategy populations play a tournament each generation; winners
              mutate to seed the next. Watch the meta evolve.
            </p>
          </EuiText>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiButton onClick={run} isLoading={busy} fill>
            Run co-evolution
          </EuiButton>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer />
      {error && <EuiCallOut title={error} color="danger" iconType="alert" />}
      {result && (
        <>
          <EuiText>
            <p>
              {result.generations} generations · population {result.population_size}/role
              · evolving {result.evolve_roles.join(", ")} · seed {result.seed}
            </p>
            <h3>Champions</h3>
            <p>
              Buyer <EuiCode>{result.buyer_champion.genome_id}</EuiCode>{" "}
              (fitness {result.buyer_champion.fitness.toFixed(3)}): {genes(result.buyer_champion)}
            </p>
            <p>
              Seller <EuiCode>{result.seller_champion.genome_id}</EuiCode>{" "}
              (fitness {result.seller_champion.fitness.toFixed(3)}): {genes(result.seller_champion)}
            </p>
            <h3>Per-generation fitness</h3>
          </EuiText>
          <EuiSpacer size="s" />
          <EuiBasicTable
            items={result.generation_records.map((r) => ({ ...r, key: r.generation }))}
            columns={genColumns}
          />
          <EuiSpacer />
          <EuiText>
            <h3>Buyer champion lineage</h3>
            <p>
              {result.buyer_champion_lineage
                .map((n) => n.genome_id)
                .join(" ← ")}
            </p>
          </EuiText>
        </>
      )}
    </EuiPanel>
  );
}
