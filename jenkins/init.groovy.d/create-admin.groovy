/* Reto 7 P1: crea el usuario admin inicial de forma idempotente.
 * Se ejecuta en cada arranque.
 *
 * Proyecto Final (cero secretos): la contraseña NO está en el código. Llega
 * como Docker secret en /run/secrets/jenkins_admin_password (archivo
 * secrets/jenkins_admin_password generado por scripts/setup-secrets.sh).
 * Si el secreto falta, no se crea ninguna cuenta con contraseña fija.
 */
import jenkins.model.*
import hudson.security.*

def secretFile = new File('/run/secrets/jenkins_admin_password')
def instance = Jenkins.getInstanceOrNull()
if (instance != null) {
    if (!secretFile.exists() || secretFile.text.trim().isEmpty()) {
        println('>>> ERROR: falta el secreto jenkins_admin_password; ejecuta bash scripts/setup-secrets.sh')
        return
    }
    def password = secretFile.text.trim()
    instance.setSecurityRealm(new HudsonPrivateSecurityRealm(false))
    instance.setAuthorizationStrategy(new FullControlOnceLoggedInAuthorizationStrategy())
    try {
        HudsonPrivateSecurityRealm realm = (HudsonPrivateSecurityRealm) instance.getSecurityRealm()
        realm.createAccount('admin', password)
        println('>>> admin creado (contraseña desde Docker secret)')
    } catch (Exception e) {
        println('>>> admin ya existe, sin cambios')
    }
    instance.save()
}
