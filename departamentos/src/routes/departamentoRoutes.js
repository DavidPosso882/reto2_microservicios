import { Router } from 'express';
import { DepartamentoService } from '../service/DepartamentoService.js';

/**
 * Router factory for /departamentos endpoints.
 *
 * @param {DepartamentoService} service - the departamento business service.
 * @returns {Router} an Express router mounted at /departamentos.
 */
export function createDepartamentoRouter(service) {
  const router = Router();

  /**
   * @openapi
   * /departamentos:
   *   post:
   *     summary: Registra un nuevo departamento
   *     description: Crea un departamento y lo persiste en la base de datos.
   *     tags: [Departamentos]
   *     requestBody:
   *       required: true
   *       content:
   *         application/json:
   *           schema:
   *             $ref: '#/components/schemas/Departamento'
   *     responses:
   *       201:
   *         description: Departamento creado correctamente.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/Departamento'
   *       400:
   *         description: Campos obligatorios faltantes o id duplicado.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/ErrorEnvelope'
   *       500:
   *         description: Error interno del servidor.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/ErrorEnvelope'
   */
  router.post('/', async (req, res, next) => {
    try {
      const created = await service.register(req.body);
      res.status(201).json(created);
    } catch (err) {
      next(err);
    }
  });

  /**
   * @openapi
   * /departamentos/{id}:
   *   get:
   *     summary: Consulta un departamento por su identificador
   *     description: Devuelve el departamento cuyo id coincide con el parámetro.
   *     tags: [Departamentos]
   *     parameters:
   *       - in: path
   *         name: id
   *         required: true
   *         schema:
   *           type: string
   *         description: Identificador único del departamento.
   *     responses:
   *       200:
   *         description: Departamento encontrado.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/Departamento'
   *       404:
   *         description: El departamento no existe.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/ErrorEnvelope'
   *       500:
   *         description: Error interno del servidor.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/ErrorEnvelope'
   */
  router.get('/:id', async (req, res, next) => {
    try {
      const found = await service.getById(req.params.id);
      res.status(200).json(found);
    } catch (err) {
      next(err);
    }
  });

  /**
   * @openapi
   * /departamentos:
   *   get:
   *     summary: Lista todos los departamentos
   *     description: Devuelve un arreglo con todos los departamentos registrados.
   *     tags: [Departamentos]
   *     responses:
   *       200:
   *         description: Listado de departamentos (puede estar vacío).
   *         content:
   *           application/json:
   *             schema:
   *               type: array
   *               items:
   *                 $ref: '#/components/schemas/Departamento'
   *       500:
   *         description: Error interno del servidor.
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/ErrorEnvelope'
   */
  router.get('/', async (req, res, next) => {
    try {
      const list = await service.list();
      res.status(200).json(list);
    } catch (err) {
      next(err);
    }
  });

  return router;
}
