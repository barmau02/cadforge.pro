import { DesignPanel } from "./components/DesignPanel";
import { JobPanel } from "./components/JobPanel";
import { LogPanel } from "./components/LogPanel";
import { PrintPanel } from "./components/PrintPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { WorkflowPanel } from "./components/WorkflowPanel";
import { useStudio } from "./hooks/useStudio";
import { useUpdater } from "./hooks/useUpdater";
import "./App.css";

export default function App() {
  const studio = useStudio();
  const updater = useUpdater();

  return (
    <div
      className="shell"
      data-connected={(studio.status?.cad_ready ?? studio.status?.rpc_connected) ? "true" : "false"}
      data-busy={studio.busy ? "true" : "false"}
    >
      <Sidebar
        active={studio.section}
        onSelect={studio.setSection}
        progress={studio.sidebarProgress}
        progressLabel={studio.busy ? "Build" : "Workflow"}
      />

      <div className="workspace">
        <TopBar
          status={studio.status}
          services={studio.services}
          busy={studio.busy}
          buildPhase={studio.buildPhase}
          buildProgress={studio.buildProgressPercent}
          onStartAll={() => studio.runAction("start-all")}
          updaterSupported={updater.supported}
          updaterStatus={updater.status}
          updaterChecking={updater.checking}
          updaterReady={updater.readyToInstall}
          onCheckUpdates={updater.check}
          onInstallUpdate={updater.install}
        />

        <main className="content" id="main-content">
          {studio.section === "workflow" && (
            <WorkflowPanel
              workflow={studio.workflow}
              busy={studio.busy}
              actionLabel={studio.actionLabel}
              onAction={studio.runAction}
            />
          )}

          {studio.section === "design" && (
            <div className="design-page">
              <DesignPanel
                prompt={studio.prompt}
                code={studio.code}
                previewError={studio.previewError}
                stlUrl={studio.stlUrl}
                loopProgress={studio.loopProgress}
                status={studio.status}
                aiModels={studio.aiModels}
                conceptImage={studio.conceptImage}
                busy={studio.busy}
                buildPhase={studio.buildPhase}
                modelReady={studio.modelReady}
                activeJobTitle={studio.activeJobTitle}
                activeJobDoc={studio.activeJobDoc}
                onPromptChange={studio.setPrompt}
                onCodeChange={studio.setCode}
                onModelChange={studio.setAiModel}
                onImageAttach={studio.attachConceptImage}
                onImageClear={studio.clearConceptImage}
                onBuild={() => studio.runAction("prompt-build")}
                onShowFreecad={() => studio.runAction("show-freecad")}
                onRunCode={() => studio.runAction("run-code")}
                onRefreshPreview={() => studio.runAction("refresh-preview")}
                featureTree={studio.featureTree}
                featureTreeLoading={studio.featureTreeLoading}
                onRefreshFeatureTree={() => studio.loadFeatureTree()}
                onPatchFeatureParam={studio.patchFeatureParam}
                contextGlobal={studio.contextGlobal}
                onContextGlobalChange={studio.setContextGlobal}
                contextGlobalHint={studio.contextGlobalHint}
                contextViewSpecs={studio.contextViewSpecs}
                generatedContextImages={studio.generatedContextImages}
                contextGenerating={studio.contextGenerating}
                onGenerateContextPreviews={(label) => void studio.generateContextPreviews(label)}
                onContextViewSpecChange={studio.updateContextViewSpec}
                onToggleContextView={studio.toggleContextView}
              />
              <JobPanel
                  jobs={studio.jobs}
                  activeJobId={studio.activeJobId}
                  busy={studio.busy}
                  onCreate={() => studio.createJob("New part")}
                  onSelect={studio.selectJob}
                  onRename={studio.renameJob}
                onDelete={studio.deleteJob}
              />
            </div>
          )}

          {studio.section === "settings" && (
            <SettingsPanel
              status={studio.status}
              onSaved={() => {
                void studio.refresh();
                void studio.loadAiModels();
              }}
            />
          )}

          {studio.section === "print" && (
            <PrintPanel
              status={studio.status}
              busy={studio.busy}
              stlUrl={studio.stlUrl}
              activeJobId={studio.activeJobId}
              onExport={() => studio.runAction("export-stl")}
              onSlicer={() => studio.runAction("open-slicer")}
              onSlice={() => studio.runAction("slice-gcode")}
              onReslice={() => studio.runAction("reslice-gcode")}
              onSend={() => studio.runAction("send-print")}
              onDiscover={studio.discoverPrinter}
              onStartAll={() => studio.runAction("start-all")}
              onGoDesign={() => studio.setSection("design")}
              onGoSettings={() => studio.setSection("settings")}
            />
          )}

          {studio.section === "logs" && <LogPanel logs={studio.logs} />}
        </main>
      </div>
    </div>
  );
}