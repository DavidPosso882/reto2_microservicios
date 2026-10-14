/* Reto 7 P1: crea el usuario admin inicial (admin/admin) de forma idempotente.
 * Se ejecuta en cada arranque; si el usuario ya existe no hace nada.
 * Credenciales de demostración documentadas en el README (entorno académico).
 */
import jenkins.model.*
import hudson.security.*

def instance = Jenkins.getInstanceOrNull()
if (instance != null) {
    instance.setSecurityRealm(new HudsonPrivateSecurityRealm(false))
    instance.setAuthorizationStrategy(new FullControlOnceLoggedInAuthorizationStrategy())
    try {
        HudsonPrivateSecurityRealm realm = (HudsonPrivateSecurityRealm) instance.getSecurityRealm()
        realm.createAccount('admin', 'admin')
        println('>>> admin creado')
    } catch (Exception e) {
        println('>>> admin ya existe, sin cambios')
    }
    instance.save()
}
