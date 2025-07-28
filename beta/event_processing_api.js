/**
 * Sonrai JIT Event Processing REST API
 * Endpoint: /api/x_custom/events/v1/process
 * Methods: POST only - Al        // Log the incoming event
        gs.info('Processing event: ' + eventData.eventName + ' (ID: ' + eventData.eventId + ')');Sonrai JIT events come in via POST
 * Authentication: ServiceNow OAuth 2.0 (Bearer token)
 * Handles Sonrai JIT lifecycle events: jit.approved, jit.expired, jit.revoked, jit.summarycreated
 * Links events using jitSessionId field
 * 
 * Event Flow:
 * 1. jit.approved -> Creates incident with "In Progress" status
 * 2. jit.expired/jit.revoked -> Updates incident to "Resolved" status
 * 3. jit.summarycreated -> Adds activity summary and closes incident
 */

(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    
    // Simple method validation - ServiceNow REST APIs are POST by default
    var method = request.getRequestMethod() || 'POST';
    if (method !== 'POST') {
        response.setStatus(405);
        response.setHeader('Allow', 'POST');
        response.setBody({
            error: 'Method Not Allowed',
            message: 'This endpoint only accepts POST requests'
        });
        return;
    }
    
    // Validate JSON body is present
    if (!request.body || typeof request.body !== 'object') {
        response.setStatus(400);
        response.setBody({
            error: 'Bad Request',
            message: 'POST request with JSON body required'
        });
        return;
    }
    
    try {
        handleEventProcessing(request, response);
    } catch (error) {
        gs.error('Event Processing API Error: ' + error.message);
        response.setStatus(500);
        response.setBody({
            error: 'Internal server error',
            message: error.message
        });
    }

    function handleEventProcessing(req, res) {
        // Parse event data from request body - handle different ServiceNow body formats
        var eventData;
        
        try {
            if (req.body && typeof req.body === 'object') {
                // Try direct access first
                if (req.body.eventName && req.body.eventId) {
                    eventData = req.body;
                }
                // Try if data is wrapped in a 'data' property
                else if (req.body.data && req.body.data.eventName && req.body.data.eventId) {
                    eventData = req.body.data;
                }
                // Try if body is a string that needs parsing
                else if (typeof req.body === 'string') {
                    eventData = JSON.parse(req.body);
                }
                // Last resort - use the body as-is
                else {
                    eventData = req.body;
                }
            } else if (typeof req.body === 'string') {
                eventData = JSON.parse(req.body);
            } else {
                eventData = req.body;
            }
            
            gs.info('Parsed event data structure - eventName: ' + (eventData ? eventData.eventName : 'missing') + ', eventId: ' + (eventData ? eventData.eventId : 'missing'));
            
        } catch (parseError) {
            gs.error('Error parsing request body: ' + parseError.message);
            res.setStatus(400);
            res.setBody({
                error: 'Invalid JSON in request body',
                message: parseError.message
            });
            return;
        }
        
        // Validate required fields
        if (!eventData || !eventData.eventName || !eventData.eventId) {
            res.setStatus(400);
            res.setBody({
                error: 'Missing required fields',
                required: ['eventName', 'eventId'],
                debug_info: {
                    received_body_type: typeof req.body,
                    received_eventData_type: typeof eventData,
                    has_eventName: !!(eventData && eventData.eventName),
                    has_eventId: !!(eventData && eventData.eventId),
                    eventData_keys: eventData ? Object.keys(eventData) : [],
                    body_preview: JSON.stringify(req.body).substring(0, 200)
                }
            });
            return;
        }
        
        // Log the incoming event
        gs.info('[JIT API] Processing event: ' + eventData.eventName + ' (ID: ' + eventData.eventId + ')');
        
        // Route to appropriate handler based on eventName
        switch(eventData.eventName) {
            case 'jit.approved':
                handleJitApprovedEvent(eventData, res);
                break;
            case 'jit.expired':
                handleJitExpiredEvent(eventData, res);
                break;
            case 'jit.revoked':
                handleJitRevokedEvent(eventData, res);
                break;
            case 'jit.summarycreated':
                handleJitSummaryCreatedEvent(eventData, res);
                break;
            default:
                res.setStatus(400);
                res.setBody({
                    error: 'Unsupported event type',
                    eventName: eventData.eventName,
                    supported_events: ['jit.approved', 'jit.expired', 'jit.revoked', 'jit.summarycreated']
                });
        }
    }

    function handleJitApprovedEvent(eventData, res) {
        try {
            var payload = eventData.payload;
            
            // Validate required fields
            if (!payload.jitSessionId) {
                res.setStatus(400);
                res.setBody({
                    error: 'Missing required field: jitSessionId',
                    eventName: eventData.eventName
                });
                return;
            }
            
            // Check if incident already exists for this jitSessionId
            var existingIncident = findIncidentByJitSessionId(payload.jitSessionId);
            if (existingIncident) {
                res.setStatus(409);
                res.setBody({
                    error: 'Incident already exists for this jitSessionId',
                    jitSessionId: payload.jitSessionId,
                    existing_incident: existingIncident.number,
                    incident_id: existingIncident.sys_id
                });
                return;
            }
            
            // Create incident for JIT approval tracking
            var gr = new GlideRecord('incident');
            gr.newRecord();
            gr.setValue('short_description', 'JIT Access Approved: ' + payload.identityFriendlyName + ' - ' + payload.scopeFriendlyName);
            gr.setValue('description', buildJitApprovedDescription(payload));
            gr.setValue('category', 'Security');
            gr.setValue('subcategory', 'Access Management');
            gr.setValue('urgency', '3'); // Low urgency for approved requests
            gr.setValue('impact', '3');
            gr.setValue('state', '2'); // In Progress (JIT session is actively running)
            
            // Set hard-coded assignment group (Cloud Architecture)
            var assignmentGroupId = getAssignmentGroupByName('Cloud Architecture');
            if (assignmentGroupId) {
                gr.setValue('assignment_group', assignmentGroupId);
            }
            
            // Set hard-coded contact type and location
            gr.setValue('contact_type', 'monitoring system');
            
            var locationId = getLocationByName('Boston');
            if (locationId) {
                gr.setValue('location', locationId);
            }
            
            // Set caller_id
            var callerId = getUserByEmail(payload.requesterEmail);
            if (callerId) {
                gr.setValue('caller_id', callerId);
            } else {
                gr.setValue('caller_id', gs.getUserID());
            }
            
            // Build work notes with consistent formatting and include both comments
            var approvalNote = '--- JIT SESSION APPROVED ---\n';
            approvalNote += 'Session approved at: ' + parseTimestamp(payload.actionedAt, 'actionedAt') + '\n';
            approvalNote += 'Approved by: ' + payload.actionedByFriendlyName + '\n';
            approvalNote += 'Session ID: ' + payload.jitSessionId + '\n';
            
            // Add requester comment if present
            if (payload.requesterComment && payload.requesterComment.trim()) {
                approvalNote += 'Requester comment: ' + payload.requesterComment.trim() + '\n';
            }
            
            // Add approver comment if present
            if (payload.comment && payload.comment.trim()) {
                approvalNote += 'Approver comment: ' + payload.comment.trim() + '\n';
            }
            
            approvalNote += 'Event processed at: ' + new GlideDateTime().toString() + '\n';
            approvalNote += 'Event ID: ' + eventData.eventId + '\n';
            
            gr.work_notes = approvalNote;
            
            // Store tracking fields for event correlation using standard ServiceNow fields only
            gr.setValue('correlation_id', payload.jitSessionId); // Primary tracking field
            gr.setValue('correlation_display', 'JIT Session: ' + payload.jitSessionId);
            gr.setValue('external_reference_id', payload.pondRequestId); // Secondary correlation
            
            var incidentId = gr.insert();
            
            if (incidentId) {
                // Refresh to get the generated incident number
                gr.get(incidentId);
                
                // Create approval record
                createApprovalRecord(eventData, incidentId);
                
                gs.info('JIT Approved incident created: ' + gr.getDisplayValue('number') + ' for jitSessionId: ' + payload.jitSessionId);
                
                res.setStatus(201);
                res.setBody({
                    result: {
                        event_processed: true,
                        event_name: eventData.eventName,
                        incident_id: incidentId,
                        incident_number: gr.getDisplayValue('number'),
                        pond_request_id: payload.pondRequestId,
                        jit_session_id: payload.jitSessionId,
                        correlation_id: payload.jitSessionId,
                        status: 'JIT access approved and tracked',
                        comments_included: {
                            requester_comment: !!(payload.requesterComment && payload.requesterComment.trim()),
                            approver_comment: !!(payload.comment && payload.comment.trim())
                        }
                    }
                });
            } else {
                res.setStatus(500);
                res.setBody({
                    error: 'Failed to create incident',
                    eventName: eventData.eventName,
                    jitSessionId: payload.jitSessionId
                });
            }
            
        } catch (error) {
            gs.error('Error processing JIT approved event: ' + error.message);
            res.setStatus(500);
            res.setBody({
                error: 'Failed to process JIT approved event',
                message: error.message,
                jitSessionId: eventData.payload ? eventData.payload.jitSessionId : 'unknown'
            });
        }
    }

    // Helper functions for event processing and data handling
    
    function findIncidentByJitSessionId(jitSessionId) {
        if (!jitSessionId) return null;
        
        var gr = new GlideRecord('incident');
        gr.addQuery('correlation_id', jitSessionId); // Using standard correlation_id field
        gr.query();
        
        if (gr.next()) {
            return {
                sys_id: gr.getUniqueValue(),
                number: gr.getDisplayValue('number'),
                state: gr.getValue('state'),
                correlation_id: gr.getValue('correlation_id'),
                external_reference_id: gr.getValue('external_reference_id')
            };
        }
        
        return null;
    }

    function handleJitExpiredEvent(eventData, res) {
        handleJitClosedEvent(eventData, res, false);
    }

    function handleJitRevokedEvent(eventData, res) {
        handleJitClosedEvent(eventData, res, true);
    }

    function handleJitClosedEvent(eventData, res, isRevoked) {
        try {
            var payload = eventData.payload;
            var eventType = isRevoked ? 'revoked' : 'expired';
            
            // Validate required fields
            if (!payload.jitSessionId) {
                res.setStatus(400);
                res.setBody({
                    error: 'Missing required field: jitSessionId',
                    eventName: eventData.eventName
                });
                return;
            }
            
            // Find the original incident
            var existingIncident = findIncidentByJitSessionId(payload.jitSessionId);
            if (!existingIncident) {
                res.setStatus(404);
                res.setBody({
                    error: 'No incident found for jitSessionId',
                    jitSessionId: payload.jitSessionId,
                    eventName: eventData.eventName
                });
                return;
            }
            
            // Update the incident
            var gr = new GlideRecord('incident');
            if (gr.get(existingIncident.sys_id)) {
                // Build work notes
                var statusNote = '--- JIT SESSION ' + eventType.toUpperCase() + ' ---\n';
                if (isRevoked) {
                    statusNote += 'Session revoked at: ' + parseTimestamp(payload.actionedAt, 'actionedAt') + '\n';
                    statusNote += 'Revoked by: ' + payload.actionedByFriendlyName + '\n';
                } else {
                    statusNote += 'Session expired at: ' + parseTimestamp(payload.expireAt, 'expireAt') + '\n';
                }
                statusNote += 'Event processed at: ' + new GlideDateTime().toString() + '\n';
                statusNote += 'Event ID: ' + eventData.eventId + '\n';
                
                // Update incident fields
                var originalWorkNotes = gr.getValue('work_notes') || '';
                var newWorkNotes = originalWorkNotes ? originalWorkNotes + '\n\n' + statusNote : statusNote;
                
                gr.work_notes = newWorkNotes;
                gr.setValue('state', '6'); // Resolved
                gr.setValue('close_notes', 'JIT session ' + eventType + (isRevoked ? ' by ' + payload.actionedByFriendlyName : ''));
                gr.setValue('resolved_at', new GlideDateTime());
                gr.setValue('resolved_by', gs.getUserID());
                gr.setValue('close_code', 'Closed/Resolved by caller');
                
                var updateResult = gr.update();
                
                if (!updateResult) {
                    // Try force update if normal update fails
                    gr.setWorkflow(false);
                    updateResult = gr.update();
                }
                
                var responseBody = {
                    result: {
                        event_processed: true,
                        event_name: eventData.eventName,
                        incident_id: existingIncident.sys_id,
                        incident_number: gr.getDisplayValue('number'),
                        pond_request_id: payload.pondRequestId,
                        jit_session_id: payload.jitSessionId,
                        status: 'JIT ' + eventType + ' recorded, incident resolved'
                    }
                };
                
                if (isRevoked) {
                    responseBody.result.revoked_by = payload.actionedByFriendlyName;
                }
                
                res.setStatus(200);
                res.setBody(responseBody);
            } else {
                res.setStatus(500);
                res.setBody({
                    error: 'Failed to update incident',
                    incident_id: existingIncident.sys_id
                });
            }
            
        } catch (error) {
            gs.error('Error processing JIT ' + (isRevoked ? 'revoked' : 'expired') + ' event: ' + error.message);
            res.setStatus(500);
            res.setBody({
                error: 'Failed to process JIT ' + (isRevoked ? 'revoked' : 'expired') + ' event',
                message: error.message
            });
        }
    }
    function handleJitSummaryCreatedEvent(eventData, res) {
        try {
            var payload = eventData.payload;
            
            // For jit.summarycreated events, the session ID is in payload.summary.sessionId
            var jitSessionId = payload.summary && payload.summary.sessionId;
            
            // Validate required fields
            if (!jitSessionId) {
                res.setStatus(400);
                res.setBody({
                    error: 'Missing required field: payload.summary.sessionId',
                    eventName: eventData.eventName,
                    payload_structure: {
                        has_summary: !!(payload.summary),
                        summary_keys: payload.summary ? Object.keys(payload.summary) : [],
                        has_sessionId: !!(payload.summary && payload.summary.sessionId)
                    }
                });
                return;
            }
            
            // Find the original incident created by jit.approved
            var existingIncident = findIncidentByJitSessionId(jitSessionId);
            if (!existingIncident) {
                res.setStatus(404);
                res.setBody({
                    error: 'No incident found for jitSessionId',
                    jitSessionId: jitSessionId,
                    eventName: eventData.eventName,
                    message: 'The corresponding jit.approved incident must exist before processing summary'
                });
                return;
            }
            
            // Update the existing incident with summary and close it
            var gr = new GlideRecord('incident');
            if (gr.get(existingIncident.sys_id)) {
                gs.info('JIT Summary: Found incident ' + gr.getDisplayValue('number') + ' in state: ' + gr.getValue('state'));
                
                var summaryNote = '--- JIT SESSION ACTIVITY SUMMARY ---\n';
                summaryNote += 'Summary created at: ' + new GlideDateTime().toString() + '\n';
                summaryNote += 'Event ID: ' + eventData.eventId + '\n';
                summaryNote += 'Summary ID: ' + (payload.summary.id || 'Unknown') + '\n';
                summaryNote += 'Summary Status: ' + (payload.summary.status || 'Unknown') + '\n';
                
                // Add regions if available
                if (payload.summary.regions && payload.summary.regions.length > 0) {
                    summaryNote += 'Regions Accessed: ' + payload.summary.regions.join(', ') + '\n';
                }
                
                // Add summary details if available
                if (payload.summary.summary) {
                    // Keep plain text formatting for work notes (no HTML)
                    summaryNote += '\nActivity Summary:\n' + payload.summary.summary + '\n';
                }
                
                // Add session details if available
                if (payload.session) {
                    summaryNote += '\nSession Details:\n';
                    if (payload.session.identity) {
                        summaryNote += '- Identity: ' + payload.session.identity + '\n';
                    }
                    if (payload.session.scope) {
                        summaryNote += '- Scope: ' + payload.session.scope + '\n';
                    }
                    if (payload.session.permissionSet && payload.session.permissionSet.name) {
                        summaryNote += '- Permission Set: ' + payload.session.permissionSet.name + '\n';
                    }
                    if (payload.session.pondRequestId) {
                        summaryNote += '- Pond Request ID: ' + payload.session.pondRequestId + '\n';
                    }
                    if (payload.session.approvedAt) {
                        var approvedAtTime = parseTimestamp(payload.session.approvedAt, 'session.approvedAt');
                        summaryNote += '- Approved At: ' + approvedAtTime + '\n';
                    }
                    if (payload.session.expiry) {
                        var expiryTime = parseTimestamp(payload.session.expiry, 'session.expiry');
                        summaryNote += '- Expired At: ' + expiryTime + '\n';
                    }
                }
                
                // Add work notes using direct property assignment (preferred for journal fields)
                // This ensures proper formatting in ServiceNow Activities without HTML markup
                gr.work_notes = summaryNote;
                gr.setValue('state', '7'); // Closed
                gr.setValue('close_notes', 'JIT session completed with activity summary attached');
                gr.setValue('closed_at', new GlideDateTime());
                
                var updateResult = gr.update();
                
                if (updateResult) {
                    gs.info('JIT Summary: Successfully updated incident ' + gr.getDisplayValue('number') + ' to state 7 (Closed)');
                } else {
                    gs.error('JIT Summary: Failed to update incident ' + gr.getDisplayValue('number') + ' - update() returned false');
                }
                
                gs.info('JIT Summary event processed for incident: ' + gr.getDisplayValue('number') + ' (jitSessionId: ' + jitSessionId + ') - Incident closed');
                
                res.setStatus(200);
                res.setBody({
                    result: {
                        event_processed: true,
                        event_name: eventData.eventName,
                        incident_id: existingIncident.sys_id,
                        incident_number: gr.getDisplayValue('number'),
                        pond_request_id: payload.session ? payload.session.pondRequestId : 'unknown',
                        jit_session_id: jitSessionId,
                        summary_id: payload.summary.id,
                        summary_status: payload.summary.status,
                        status: 'JIT summary recorded, incident closed'
                    }
                });
            } else {
                res.setStatus(500);
                res.setBody({
                    error: 'Failed to update incident',
                    incident_id: existingIncident.sys_id,
                    jitSessionId: jitSessionId
                });
            }
            
        } catch (error) {
            gs.error('Error processing JIT summary created event: ' + error.message);
            res.setStatus(500);
            res.setBody({
                error: 'Failed to process JIT summary created event',
                message: error.message,
                jitSessionId: (eventData.payload && eventData.payload.summary && eventData.payload.summary.sessionId) ? eventData.payload.summary.sessionId : 'unknown'
            });
        }
    }

    function buildJitApprovedDescription(payload) {
        var description = 'JIT Access Request Approved\n\n';
        description += 'Request Details:\n';
        description += '- Requester: ' + payload.identityFriendlyName + ' (' + payload.requesterEmail + ')\n';
        description += '- Account: ' + payload.accountFriendlyName + ' (' + payload.account + ')\n';
        description += '- Organization Scope: ' + payload.scopeFriendlyName + '\n';
        description += '- Session Duration: ' + payload.requestedDuration + ' hours\n';
        description += '- JIT Session ID: ' + payload.jitSessionId + '\n';
        description += '- PoD Request ID: ' + payload.pondRequestId + '\n';
        
        // Parse timestamps using helper function
        var expireAtTime = parseTimestamp(payload.expireAt, 'expireAt');
        var revokeAtTime = parseTimestamp(payload.revokeAt, 'revokeAt');
        var actionedAtTime = parseTimestamp(payload.actionedAt, 'actionedAt');
        
        description += '- Expires At: ' + expireAtTime + '\n';
        description += '- Revoke At: ' + revokeAtTime + '\n\n';
        
        description += 'Approval Details:\n';
        description += '- Approved By: ' + payload.actionedByFriendlyName + '\n';
        description += '- Approved At: ' + actionedAtTime + '\n';
        description += '- Time to Completion: ' + payload.timeToCompletion + 'ms\n';
        
        // Include both comments if they exist
        var hasComments = false;
        if (payload.requesterComment && payload.requesterComment.trim()) {
            description += '- Requester Comment: ' + payload.requesterComment.trim() + '\n';
            hasComments = true;
        }
        
        if (payload.comment && payload.comment.trim()) {
            description += '- Approver Comment: ' + payload.comment.trim() + '\n';
            hasComments = true;
        }
        
        if (!hasComments) {
            description += '- Comments: No comments provided\n';
        }
        
        description += '\n';
        
        description += 'This incident will be updated when the JIT session expires or is revoked.';
        
        return description;
    }

    // Helper functions for building descriptions and handling data
    
    function parseTimestamp(timestamp, fieldName) {
        if (!timestamp) return 'Unknown';
        
        try {
            var timestampMs = parseInt(timestamp);
            var gdt = new GlideDateTime();
            gdt.setValue(timestampMs);
            return gdt.getDisplayValue();
        } catch (error) {
            gs.warn('Error parsing ' + fieldName + ' timestamp: ' + timestamp);
            return 'Invalid timestamp: ' + timestamp;
        }
    }
    
    function getUserByEmail(email) {
        if (!email) return '';
        
        var userGr = new GlideRecord('sys_user');
        userGr.addQuery('email', email);
        userGr.query();
        
        if (userGr.next()) {
            return userGr.getUniqueValue();
        }
        
        gs.warn('No user found with email: ' + email);
        return '';
    }
    
    function createApprovalRecord(eventData, incidentId) {
        try {
            var payload = eventData.payload;
            var approvalGr = new GlideRecord('sysapproval_approver');
            
            approvalGr.newRecord();
            approvalGr.setValue('document_id', incidentId);
            approvalGr.setValue('table', 'incident');
            approvalGr.setValue('state', 'approved');
            approvalGr.setValue('approver', getUserByEmail(payload.actionedByFriendlyName));
            approvalGr.setValue('comments', payload.comment || 'JIT access approved via automated system');
            approvalGr.insert();
            
        } catch (error) {
            gs.error('Error creating approval record: ' + error.message);
        }
    }
    
    function getAssignmentGroupByName(groupName) {
        if (!groupName) return '';
        
        var groupGr = new GlideRecord('sys_user_group');
        groupGr.addQuery('name', groupName);
        groupGr.query();
        
        if (groupGr.next()) {
            return groupGr.getUniqueValue();
        }
        
        gs.warn('No assignment group found with name: ' + groupName);
        return '';
    }
    
    function getLocationByName(locationName) {
        if (!locationName) return '';
        
        var locationGr = new GlideRecord('cmn_location');
        locationGr.addQuery('name', locationName);
        locationGr.query();
        
        if (locationGr.next()) {
            return locationGr.getUniqueValue();
        }
        
        gs.warn('No location found with name: ' + locationName);
        return '';
    }

})(request, response);
