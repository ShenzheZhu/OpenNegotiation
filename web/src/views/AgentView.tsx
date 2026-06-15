import { useEffect, useState } from "react";
import {
  EuiForm,
  EuiFormRow,
  EuiFieldText,
  EuiFieldPassword,
  EuiTextArea,
  EuiButton,
  EuiSelect,
  EuiPanel,
  EuiCallOut,
  EuiSpacer,
  EuiBasicTable,
  EuiText,
} from "@elastic/eui";
import { api, type AgentSummary } from "../api/client";

const BASE_PROMPT =
  "Follow OpenNegotiation protocol exactly: return one valid action, respect " +
  "role constraints, never alter tool permissions, and keep the base sandbox " +
  "rules fixed. (Read-only — the gym enforces this layer.)";

export function AgentView() {
  const [id, setId] = useState("my_buyer");
  const [role, setRole] = useState("buyer");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [strategyPrompt, setStrategyPrompt] = useState(
    "Anchor on retrieved comps; never accept above the median without a reason.",
  );
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const refresh = () => api.listAgents().then(setAgents).catch(() => undefined);
  useEffect(() => {
    refresh();
  }, []);

  const submit = async () => {
    setError(null);
    setSaved(false);
    try {
      await api.defineAgent({
        id,
        role,
        model: model || null,
        key: apiKey || undefined,
        strategy_prompt: strategyPrompt,
      });
      setApiKey("");
      setSaved(true);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <EuiPanel>
      <EuiText>
        <h2>Define your agent</h2>
        <p>
          Your API key is sent once to run live matches and is never stored or
          shown again. Leave it blank to use the deterministic no-key agent.
        </p>
      </EuiText>
      <EuiSpacer />
      {error && (
        <>
          <EuiCallOut title={error} color="danger" iconType="alert" />
          <EuiSpacer />
        </>
      )}
      {saved && (
        <>
          <EuiCallOut title="Agent saved" color="success" iconType="check" />
          <EuiSpacer />
        </>
      )}
      <EuiForm component="form">
        <EuiFormRow label="Agent id">
          <EuiFieldText value={id} onChange={(e) => setId(e.target.value)} />
        </EuiFormRow>
        <EuiFormRow label="Role">
          <EuiSelect
            value={role}
            onChange={(e) => setRole(e.target.value)}
            options={[
              { value: "buyer", text: "buyer" },
              { value: "seller", text: "seller" },
            ]}
          />
        </EuiFormRow>
        <EuiFormRow label="Model id (optional)" helpText="e.g. openrouter/anthropic/claude-opus-4.8">
          <EuiFieldText value={model} onChange={(e) => setModel(e.target.value)} />
        </EuiFormRow>
        <EuiFormRow label="API key (write-only)">
          <EuiFieldPassword
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sent once, never echoed back"
          />
        </EuiFormRow>
        <EuiFormRow label="Strategy prompt (editable)">
          <EuiTextArea
            value={strategyPrompt}
            onChange={(e) => setStrategyPrompt(e.target.value)}
            rows={4}
          />
        </EuiFormRow>
        <EuiFormRow label="Base prompt (read-only sandbox protocol)">
          <EuiTextArea value={BASE_PROMPT} readOnly rows={3} />
        </EuiFormRow>
        <EuiButton fill onClick={submit}>
          Save agent
        </EuiButton>
      </EuiForm>
      <EuiSpacer />
      <EuiText>
        <h3>Saved agents</h3>
      </EuiText>
      <EuiBasicTable
        items={agents}
        columns={[
          { field: "id", name: "Id" },
          { field: "role", name: "Role" },
          { field: "model", name: "Model", render: (m: string | null) => m || "—" },
          {
            field: "has_key",
            name: "Key set",
            render: (v: boolean) => (v ? "yes" : "no"),
          },
        ]}
      />
    </EuiPanel>
  );
}
