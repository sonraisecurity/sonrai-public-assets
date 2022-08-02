#!/bin/sh

main() {
  local _principal_id="$1"
  if [ -z "${_principal_id}" ] ; then
    echo "Usage: ${0} <principal_id>" 1>&2
    exit 1
  fi
  if ! command -v az >/dev/null 2>&1 ; then
    echo "'az' not found in PATH" 1>&2
    exit 2
  fi
  # Microsoft Graph Application
  local _graph_object_id
  if ! _graph_object_id=$(az ad sp list --query "[?appDisplayName=='Microsoft Graph'].[objectId || id] | [0]" --all --out tsv --only-show-errors) ; then
    echo "Failed to locate application: Microsoft Graph" 1>&2
    exit 2
  fi
  echo "Microsoft Graph objectId: ${_graph_object_id}"
  # Directory.Read.All Application Role within Microsoft Graph Application
  local _directory_read_all
  if ! _directory_read_all=$(az ad sp show --id "${_graph_object_id}" --query "appRoles[?value=='Directory.Read.All'].id | [0]" --out tsv --only-show-errors) ; then
    echo "Failed to locate application role: Directory.Read.All (Microsoft Graph:${_graph_object_id})" 1>&2
    exit 2
  fi
  echo "Directory.Read.All (Microsoft Graph) objectId: ${_directory_read_all}"
  # AuditLog.Read.All Application Role within Microsoft Graph Application
  local _audit_log_read_all
  if ! _audit_log_read_all=$(az ad sp show --id "${_graph_object_id}" --query "appRoles[?value=='AuditLog.Read.All'].id | [0]" --out tsv --only-show-errors) ; then
    echo "Failed to locate application role: AuditLog.Read.All (Microsoft Graph:${_graph_object_id})" 1>&2
    exit 2
  fi
  echo "AuditLog.Read.All (Microsoft Graph) objectId: ${_audit_log_read_all}"
  echo "Assigning principal (${_principal_id}) Directory.Read.All (${_directory_read_all}) within Microsoft Graph (${_graph_object_id})..."
  _assign_role "${_principal_id}" "${_graph_object_id}" "${_directory_read_all}"
  echo "Assigning principal (${_principal_id}) AuditLog.Read.All (${_audit_log_read_all}) within Microsoft Graph (${_graph_object_id})..."
  _assign_role "${_principal_id}" "${_graph_object_id}" "${_audit_log_read_all}"
}

_assign_role() {
  local _principal_id="$1" _resource_id="$2" _app_role_id="$3"
  az rest --method POST \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${_principal_id}/appRoleAssignments" \
    --body "{\"principalId\": \"${_principal_id}\", \"resourceId\": \"${_resource_id}\", \"appRoleId\": \"${_app_role_id}\"}" \
    --only-show-errors
}

main "$@"