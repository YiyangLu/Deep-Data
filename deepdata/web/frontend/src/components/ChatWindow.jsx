import { MessageList } from './MessageList';
import { InputBox } from './InputBox';
import { PlotPanel } from './PlotPanel';
import { ShowPanelEdge } from './ShowPanelEdge';
import { AgentTabs } from './AgentTabs';
import { SessionTypeSelector } from './SessionTypeSelector';
import { MLEForm } from './MLEForm';
import { MLEDashboard } from './MLEDashboard';

/**
 * Main chat window container.
 *
 * Combines status bar, message list, input box, and optional plot panel.
 * Supports dynamic resizing and hide/show functionality.
 * Shows different content based on active session type.
 */
export function ChatWindow({
  sessionId,
  messages,
  stats,
  onSendMessage,
  onDeepPlot,
  onMLEStart,
  onMLEAutoFill,
  isMLEAutoFilling,
  onMLEStop,
  onMLEPause,
  onMLEResume,
  mleStatus,
  mleTree,
  mleSelectedNode,
  mleNodeLogs,
  onMLENodeSelect,
  isProcessing,
  plotUrl,
  plotVisible,
  onClosePlot,
  chatWidth,
  chatVisible,
  onResize,
  onHideChat,
  onHidePlot,
  onShowChat,
  onShowPlot,
  onSessionSwitch,
  tabs,
  activeTabIndex,
  onTabClick,
  onTabClose,
  agentTabs,
  activeAgentTabIndex,
  activeSessionType,
  onSessionTypeSelect,
  onAgentTabClick,
  onAgentTabClose,
  onNewAgentTab,
  onRenameAgentTab,
  onMleResumeFromHistory,
  onRecoverPlot,
  plotCommand,
  deepPlotReport,
  isNewSession,
  cwdInfo,
  onCwdChange,
  plotCacheClearTrigger
}) {
  // Render content based on session type
  const renderContent = () => {
    switch (activeSessionType) {
      case null:
        // Loading state - show nothing while workspace loads
        return null;

      case 'new':
        return (
          <SessionTypeSelector onSelect={onSessionTypeSelect} />
        );

      case 'mle':
        return (
          <div className="flex-1 overflow-auto p-8">
            <div className="flex justify-center">
              <MLEForm
                onStart={onMLEStart}
                onAutoFill={onMLEAutoFill}
                isAutoFilling={isMLEAutoFilling}
                defaultWorkspace={cwdInfo?.cwd}
              />
            </div>
          </div>
        );

      case 'mle_running':
        return (
          <MLEDashboard
            status={mleStatus}
            tree={mleTree}
            selectedNode={mleSelectedNode}
            nodeLogs={mleNodeLogs}
            onNodeSelect={onMLENodeSelect}
            onPause={onMLEPause}
            onResume={onMLEResume}
          />
        );

      case 'agent':
      case 'deep_plot':
      default:
        return (
          <>
            {/* Message List - key forces re-mount on tab switch to prevent stale content */}
            <MessageList
              key={agentTabs[activeAgentTabIndex]?.tab_id || 'default'}
              messages={messages}
              isLoading={activeAgentTabIndex !== null && activeAgentTabIndex >= 0 && messages.length === 0 && !isProcessing}
              deepPlotReport={deepPlotReport}
            />

            {/* Input Box with token stats */}
            <InputBox
              onSend={onSendMessage}
              onDeepPlot={onDeepPlot}
              disabled={isProcessing}
              isProcessing={isProcessing}
              sessionId={agentTabs[activeAgentTabIndex]?.session_id || sessionId}
              plotTabs={tabs}
              onRecoverPlot={onRecoverPlot}
              stats={stats}
              sessionType={activeSessionType}
              isNewSession={isNewSession}
              cwdInfo={cwdInfo}
              onCwdChange={onCwdChange}
              currentCwd={agentTabs[activeAgentTabIndex]?.current_cwd}
            />
          </>
        );
    }
  };
  return (
    <div className="flex h-screen bg-white relative">
      {/* Left side: Chat interface */}
      {chatVisible ? (
        <div
          className="chat-panel flex flex-col min-w-0 h-full"
          style={(tabs.length > 0 && plotVisible && activeSessionType === 'agent') ? { width: `${chatWidth}%` } : { width: '100%' }}
        >
          {/* Agent Tabs - always visible (contains history dropdown) */}
          <AgentTabs
            tabs={agentTabs}
            activeTabIndex={activeAgentTabIndex}
            onTabClick={onAgentTabClick}
            onTabClose={onAgentTabClose}
            onRenameTab={onRenameAgentTab}
            showButtons={tabs.length === 0}
            onNewTab={onNewAgentTab}
            currentSessionId={sessionId}
            onSessionSwitch={onSessionSwitch}
            onMleResume={onMleResumeFromHistory}
          />

          {/* Content based on session type */}
          {renderContent()}
        </div>
      ) : (
        /* Show chat edge when hidden - hover to reveal show button */
        <ShowPanelEdge
          side="left"
          onShow={onShowChat}
          panelName="chat panel"
        />
      )}

      {/* Right side: Plot panel or edge */}
      {tabs.length > 0 ? (
        plotVisible ? (
          <div className="flex-1 min-w-0">
            <PlotPanel
              plotUrl={plotUrl}
              onClose={onClosePlot}
              tabs={tabs}
              activeTabIndex={activeTabIndex}
              onTabClick={onTabClick}
              onTabClose={onTabClose}
              onResize={chatVisible ? onResize : null}
              onHideLeft={chatVisible ? onHideChat : null}
              onHideRight={onHidePlot}
              showButtons={tabs.length > 0}
              onNewTab={onNewAgentTab}
              currentSessionId={sessionId}
              onSessionSwitch={onSessionSwitch}
              plotCommand={plotCommand}
              cacheClearTrigger={plotCacheClearTrigger}
            />
          </div>
        ) : (
          /* Show plot edge when hidden - hover to reveal show button */
          <>
            {/* Spacer to push edge to the right side */}
            <div className="flex-1" />
            <ShowPanelEdge
              side="right"
              onShow={onShowPlot}
              panelName="plot panel"
            />
          </>
        )
      ) : null}
    </div>
  );
}
